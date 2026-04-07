mod auth;
mod config;
mod sysinfo_collector;
mod command_executor;
mod file_transfer;
mod websocket_client;

use std::{fs, sync::Arc};
use anyhow::{Context, Result};
use tracing::info;

#[tokio::main]
async fn main() -> Result<()> {
    rustls::crypto::ring::default_provider()
        .install_default()
        .expect("Failed to install rustls crypto provider");

    tracing_subscriber::fmt::init();

    let config_path = "config.json";
    let config_str  = fs::read_to_string(config_path)
        .with_context(|| format!(
            "Cannot read '{}'. Current dir: {}",
            config_path,
            std::env::current_dir().unwrap_or_default().display()
        ))?;
    let config_str  = config_str.strip_prefix('\u{FEFF}').unwrap_or(&config_str);

    let cfg: config::Config = serde_json::from_str(config_str)
        .with_context(|| format!("Invalid JSON in '{config_path}'"))?;
    let cfg = Arc::new(cfg);
    info!("Config loaded. Server: {}", cfg.server_url);

    let http_client = auth::build_http_client(&cfg)
        .context("Failed to build HTTP client")?;

    let state = auth::ensure_registered(&http_client, &cfg)
        .await
        .context("Agent registration failed")?;

    let agent_id = state.agent_id.unwrap();
    let token    = state.token.unwrap();
    info!("Agent ID: {agent_id}");

    // Heartbeat в фоне
    {
        let c  = http_client.clone();
        let cf = cfg.clone();
        let id = agent_id.clone();
        let tk = token.clone();
        tokio::spawn(async move {
            loop {
                let si  = sysinfo_collector::collect();
                let url = format!("{}/api/v1/agents/{}/heartbeat", cf.server_url, id);
                match c.post(&url)
                    .header("X-Agent-ID",    &id)
                    .header("X-Agent-Token", &tk)
                    .json(&serde_json::json!({"sysinfo": si}))
                    .send().await
                {
                    Ok(r)  => info!("Heartbeat: {}", r.status()),
                    Err(e) => tracing::warn!("Heartbeat failed: {e}"),
                }
                tokio::time::sleep(
                    std::time::Duration::from_secs(cf.heartbeat_secs)
                ).await;
            }
        });
    }

    // WebSocket — всегда plain (TLS терминируется на уровне TCP через native-tls автоматически)
    info!("Starting WebSocket: {}", cfg.ws_url);
    websocket_client::run_forever_plain(cfg, agent_id, token).await;

    Ok(())
}
