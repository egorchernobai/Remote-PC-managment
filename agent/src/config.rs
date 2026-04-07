use serde::{Deserialize, Serialize};
use std::fs;  // убрали path::PathBuf

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Config {
    pub server_url:     String,
    pub ws_url:         String,
    pub ca_cert_path:   String,
    pub agent_cert:     String,
    pub agent_key:      String,
    pub state_file:     String,
    pub heartbeat_secs: u64,
}

#[derive(Debug, Clone, Deserialize, Serialize, Default)]
pub struct AgentState {
    pub agent_id: Option<String>,
    pub token:    Option<String>,
}

impl AgentState {
    pub fn load(path: &str) -> Self {
        fs::read_to_string(path)
            .ok()
            .and_then(|s| serde_json::from_str(&s).ok())
            .unwrap_or_default()
    }

    pub fn save(&self, path: &str) -> anyhow::Result<()> {
        let json = serde_json::to_string_pretty(self)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            use std::io::Write;
            let mut f = fs::OpenOptions::new()
                .write(true).create(true).truncate(true)
                .mode(0o600).open(path)?;
            f.write_all(json.as_bytes())?;
        }
        #[cfg(not(unix))]
        fs::write(path, json)?;
        Ok(())
    }
}
