use anyhow::Result;
use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use std::{sync::Arc, time::Duration};
use tokio::time::sleep;
use tokio_tungstenite::{
    connect_async, connect_async_tls_with_config, tungstenite::Message, Connector,
};
use tracing::{error, info, warn};

use crate::{command_executor, config::Config, file_transfer, sysinfo_collector};

const MAX_RECONNECT_DELAY_SECS: u64 = 60;
const SYSINFO_PUSH_INTERVAL_SECS: u64 = 30;

pub async fn run_forever_plain(
    cfg: Arc<Config>,
    client: reqwest::Client,
    agent_id: String,
    token: String,
) {
    let connector = if cfg.ws_url.starts_with("wss://") {
        match build_tls_connector(&cfg.ca_cert_path, &cfg.agent_cert, &cfg.agent_key) {
            Ok(c) => Some(c),
            Err(e) => {
                tracing::error!("TLS connector error: {e}");
                return;
            }
        }
    } else {
        None
    };

    let mut delay_secs = 2u64;
    loop {
        info!("Connecting to: {}", cfg.ws_url);
        let result = match &connector {
            Some(c) => connect_tls_and_handle(&cfg, &client, &agent_id, &token, c).await,
            None => connect_plain_and_handle(&cfg, &client, &agent_id, &token).await,
        };
        match result {
            Ok(_) => {
                info!("Session ended");
                delay_secs = 2;
            }
            Err(e) => {
                warn!("WS error: {e}. Retry in {delay_secs}s...");
                sleep(Duration::from_secs(delay_secs)).await;
                delay_secs = (delay_secs * 2).min(MAX_RECONNECT_DELAY_SECS);
            }
        }
    }
}

fn build_tls_connector(ca_path: &str, cert_path: &str, key_path: &str) -> Result<Connector> {
    use rustls::{ClientConfig, RootCertStore};
    use std::fs;

    let ca_pem = fs::read(ca_path)?;
    let cert_pem = fs::read(cert_path)?;
    let key_pem = fs::read(key_path)?;

    let mut root_store = RootCertStore::empty();
    for cert in rustls_pemfile::certs(&mut ca_pem.as_slice()) {
        root_store.add(cert?)?;
    }
    let certs: Vec<_> =
        rustls_pemfile::certs(&mut cert_pem.as_slice()).collect::<std::result::Result<_, _>>()?;
    let key = rustls_pemfile::private_key(&mut key_pem.as_slice())?
        .ok_or_else(|| anyhow::anyhow!("No private key in {key_path}"))?;

    let tls_cfg = ClientConfig::builder()
        .with_root_certificates(root_store)
        .with_client_auth_cert(certs, key)?;

    Ok(Connector::Rustls(Arc::new(tls_cfg)))
}

async fn connect_tls_and_handle(
    cfg: &Config,
    client: &reqwest::Client,
    agent_id: &str,
    token: &str,
    connector: &Connector,
) -> Result<()> {
    let (ws_stream, _) =
        connect_async_tls_with_config(&cfg.ws_url, None, false, Some(connector.clone())).await?;
    handle_ws(ws_stream, cfg, client, agent_id, token).await
}

async fn connect_plain_and_handle(
    cfg: &Config,
    client: &reqwest::Client,
    agent_id: &str,
    token: &str,
) -> Result<()> {
    let (ws_stream, _) = connect_async(&cfg.ws_url).await?;
    handle_ws(ws_stream, cfg, client, agent_id, token).await
}

async fn handle_ws<S>(
    ws_stream: S,
    cfg: &Config,
    client: &reqwest::Client,
    agent_id: &str,
    token: &str,
) -> Result<()>
where
    S: futures_util::Stream<Item = Result<Message, tokio_tungstenite::tungstenite::Error>>
        + futures_util::Sink<Message, Error = tokio_tungstenite::tungstenite::Error>
        + Unpin,
{
    let (mut write, mut read) = ws_stream.split();
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<String>();

    write
        .send(Message::Text(
            json!({"agent_id": agent_id, "token": token}).to_string(),
        ))
        .await?;

    match read.next().await {
        Some(Ok(Message::Text(msg))) => {
            let v: Value = serde_json::from_str(&msg)?;
            if v["type"] != "auth_ok" {
                anyhow::bail!("Auth rejected: {msg}");
            }
            info!("WebSocket authenticated");
        }
        other => anyhow::bail!("Unexpected auth response: {other:?}"),
    }

    let sysinfo_tx = tx.clone();
    tokio::spawn(async move {
        loop {
            sleep(Duration::from_secs(SYSINFO_PUSH_INTERVAL_SECS)).await;
            let msg = json!({"type":"sysinfo","payload":sysinfo_collector::collect()}).to_string();
            if sysinfo_tx.send(msg).is_err() {
                break;
            }
        }
    });

    loop {
        tokio::select! {
            incoming = read.next() => match incoming {
                None                          => { info!("Server closed"); return Ok(()); }
                Some(Err(e))                  => return Err(e.into()),
                Some(Ok(Message::Close(_)))   => { info!("Close frame"); return Ok(()); }
                Some(Ok(Message::Ping(d)))    => { write.send(Message::Pong(d)).await?; }
                Some(Ok(Message::Text(text))) => {
                    if let Some(response) =
                        handle_server_message(&text, cfg, client, agent_id, token, tx.clone()).await
                    {
                        tx.send(response)?;
                    }
                }
                _ => {}
            },
            Some(out) = rx.recv() => { write.send(Message::Text(out)).await?; }
        }
    }
}

async fn handle_server_message(
    text: &str,
    cfg: &Config,
    client: &reqwest::Client,
    agent_id: &str,
    token: &str,
    tx: tokio::sync::mpsc::UnboundedSender<String>,
) -> Option<String> {
    let data: Value = serde_json::from_str(text).ok()?;
    match data["type"].as_str() {
        Some("execute") => {
            let cmd_id = data["command_id"].as_str().unwrap_or("").to_string();
            let command = data["command"].as_str().unwrap_or("").to_string();
            let cmd_type = data["cmd_type"].as_str().unwrap_or("shell").to_string();
            info!("Executing [{cmd_type}] id={cmd_id}");
            let cfg = cfg.clone();
            let client = client.clone();
            let agent_id = agent_id.to_string();
            let token = token.to_string();

            tokio::spawn(async move {
                let resp = match execute_server_command(
                    &cmd_id, &cmd_type, &command, &cfg, &client, &agent_id, &token,
                )
                .await
                {
                    Ok(r) => json!({"type":"command_result","command_id":r.command_id,
                                     "output":r.output,"exit_code":r.exit_code}),
                    Err(e) => {
                        error!("Exec error: {e}");
                        json!({"type":"command_result","command_id":cmd_id,
                                       "output":format!("Error: {e}"),"exit_code":-1})
                    }
                };

                if tx.send(resp.to_string()).is_err() {
                    warn!("Failed to send command result to WebSocket writer");
                }
            });
            None
        }
        Some("ping") => Some(json!({"type":"pong"}).to_string()),
        other => {
            warn!("Unknown type: {other:?}");
            None
        }
    }
}

async fn execute_server_command(
    command_id: &str,
    cmd_type: &str,
    command: &str,
    cfg: &Config,
    client: &reqwest::Client,
    agent_id: &str,
    token: &str,
) -> Result<command_executor::CommandResult> {
    if cmd_type != "file_upload" {
        return command_executor::execute(command_id, cmd_type, command).await;
    }

    let payload: Value = serde_json::from_str(command)?;
    let transfer_id = payload["transfer_id"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("Missing transfer_id"))?;
    let filename = payload["filename"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("Missing filename"))?;
    let expected_sha256 = payload["sha256"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("Missing sha256"))?;

    let saved_path = file_transfer::download_file(
        client,
        &cfg.server_url,
        transfer_id,
        agent_id,
        token,
        filename,
        expected_sha256,
    )
    .await?;

    Ok(command_executor::CommandResult {
        command_id: command_id.to_string(),
        output: format!("File saved to {saved_path}"),
        exit_code: 0,
    })
}
