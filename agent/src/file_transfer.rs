#![allow(dead_code)] 
use anyhow::Result;
use sha2::{Digest, Sha256};
use std::path::Path;
use tokio::{fs::File, io::AsyncWriteExt};

/// Скачиваем файл с сервера и проверяем SHA-256
pub async fn download_file(
    client: &reqwest::Client,
    server_url: &str,
    transfer_id: &str,
    agent_id: &str,
    token: &str,
    dest_path: &str,
    expected_sha256: &str,
) -> Result<()> {
    let url = format!("{}/api/v1/files/fetch/{}", server_url, transfer_id);
    let mut res = client.get(&url)
        .header("X-Agent-ID", agent_id)
        .header("X-Agent-Token", token)
        .send().await?;

    if !res.status().is_success() {
        anyhow::bail!("File download failed: {}", res.status());
    }

    // Проверяем, что путь не выходит за пределы разрешённой директории
    let safe_path = safe_dest_path(dest_path, "/var/rmm/files")?;
    let mut file = File::create(&safe_path).await?;
    let mut hasher = Sha256::new();

    while let Some(chunk) = res.chunk().await? {
        hasher.update(&chunk);
        file.write_all(&chunk).await?;
    }

    let actual_hash = hex::encode(hasher.finalize());
    if actual_hash != expected_sha256 {
        tokio::fs::remove_file(&safe_path).await?;
        anyhow::bail!("SHA256 mismatch: expected {expected_sha256}, got {actual_hash}");
    }
    Ok(())
}

/// Защита от path traversal
fn safe_dest_path(dest: &str, base: &str) -> Result<String> {
    let base = Path::new(base).canonicalize()?;
    let full = base.join(Path::new(dest).file_name()
        .ok_or_else(|| anyhow::anyhow!("Invalid path"))?);
    let canonical = full.canonicalize().unwrap_or(full.clone());
    if !canonical.starts_with(&base) {
        anyhow::bail!("Path traversal detected");
    }
    Ok(canonical.to_string_lossy().to_string())
}
