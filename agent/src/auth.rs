use anyhow::{bail, Result};
use reqwest::Client;
use serde::Deserialize;
use serde_json::json;
use tracing::{info, warn};

use crate::config::{AgentState, Config};
use crate::sysinfo_collector;

#[derive(Debug, Deserialize)]
struct RegisterResponse {
    agent_id: String,
    token: String,
}

pub async fn ensure_registered(client: &Client, cfg: &Config) -> Result<AgentState> {
    let mut state = AgentState::load(&cfg.state_file);

    if state.agent_id.is_some() && state.token.is_some() {
        if verify_registration(client, cfg, &state).await {
            info!(
                "Agent already registered: {}",
                state.agent_id.as_deref().unwrap()
            );
            return Ok(state);
        }
        warn!("Server doesn't recognize credentials, re-registering...");
        state = register_new(client, cfg).await?;
        state.save(&cfg.state_file)?;
        return Ok(state);
    }

    let new_state = register_new(client, cfg).await?;
    new_state.save(&cfg.state_file)?;
    Ok(new_state)
}

async fn register_new(client: &Client, cfg: &Config) -> Result<AgentState> {
    let sysinfo = sysinfo_collector::collect();
    let url = format!("{}/api/v1/agents/register", cfg.server_url);

    let res = client
        .post(&url)
        .json(&json!({
            "hostname": sysinfo.hostname,
            "os_info": sysinfo
        }))
        .send()
        .await?;

    if !res.status().is_success() {
        let status = res.status();
        let body = res.text().await.unwrap_or_default();
        bail!("Registration failed [{status}]: {body}");
    }

    let data: RegisterResponse = res.json().await?;
    info!("Registered successfully. Agent ID: {}", data.agent_id);

    Ok(AgentState {
        agent_id: Some(data.agent_id),
        token: Some(data.token),
    })
}

async fn verify_registration(client: &Client, cfg: &Config, state: &AgentState) -> bool {
    let agent_id = state.agent_id.as_deref().unwrap_or("");
    let token = state.token.as_deref().unwrap_or("");
    let url = format!("{}/api/v1/agents/{}/heartbeat", cfg.server_url, agent_id);

    client
        .post(&url)
        .header("X-Agent-ID", agent_id)
        .header("X-Agent-Token", token)
        .json(&json!({}))
        .send()
        .await
        .map(|r| r.status().is_success())
        .unwrap_or(false)
}

pub fn build_http_client(cfg: &Config) -> Result<Client> {
    use rustls::{ClientConfig, RootCertStore};
    use std::fs;

    if cfg.server_url.starts_with("http://") {
        return Ok(Client::builder()
            .timeout(std::time::Duration::from_secs(30))
            .build()?);
    }

    let ca_pem = fs::read(&cfg.ca_cert_path)?;
    let cert_pem = fs::read(&cfg.agent_cert)?;
    let key_pem = fs::read(&cfg.agent_key)?;

    let mut root_store = RootCertStore::empty();
    for cert in rustls_pemfile::certs(&mut ca_pem.as_slice()) {
        root_store.add(cert?)?;
    }
    let certs: Vec<_> =
        rustls_pemfile::certs(&mut cert_pem.as_slice()).collect::<std::result::Result<_, _>>()?;
    let key = rustls_pemfile::private_key(&mut key_pem.as_slice())?
        .ok_or_else(|| anyhow::anyhow!("No private key found in {}", cfg.agent_key))?;

    let tls_config = ClientConfig::builder()
        .with_root_certificates(root_store)
        .with_client_auth_cert(certs, key)?;

    let mut identity_pem = cert_pem.clone();
    identity_pem.extend_from_slice(&key_pem);
    let identity = reqwest::Identity::from_pem(&identity_pem)?;

    Ok(Client::builder()
        .use_preconfigured_tls(tls_config)
        .identity(identity)
        .tls_built_in_root_certs(false)
        .https_only(true)
        .timeout(std::time::Duration::from_secs(30))
        .build()?)
}
