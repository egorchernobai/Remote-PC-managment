use anyhow::{bail, Result};
use serde::{Deserialize, Serialize};
use std::process::Stdio;
use tokio::process::Command;
use tokio::time::{timeout, Duration};

#[derive(Debug, Serialize, Deserialize)]
pub struct CommandResult {
    pub command_id: String,
    pub output:     String,
    pub exit_code:  i32,
}

const CMD_TIMEOUT_SECS: u64 = 60;

pub async fn execute(
    command_id: &str,
    cmd_type:   &str,
    command:    &str,
) -> Result<CommandResult> {
    match cmd_type {
        "shell"         => run_shell(command_id, command).await,
        "script"        => run_script(command_id, command).await,
        "process_list"  => get_process_list(command_id).await,
        "process_kill"  => kill_process(command_id, command).await,
        "service_list"  => service_cmd(command_id, "list").await,
        "service_start" => service_cmd(command_id, &format!("start {command}")).await,
        "service_stop"  => service_cmd(command_id, &format!("stop {command}")).await,
        _               => bail!("Unknown command type: {cmd_type}"),
    }
}

// ── run_shell ────────────────────────────────────────────────────────────────

async fn run_shell(command_id: &str, cmd: &str) -> Result<CommandResult> {
    #[cfg(target_os = "windows")]
    let out = {
        let cmd_lower = cmd.to_lowercase();
        let blocked = [
            "format ", "del /f /s /q c:", "rd /s /q c:",
            "shutdown", "reg delete",
        ];
        for b in &blocked {
            if cmd_lower.contains(b) {
                bail!("Command blocked by policy: {b}");
            }
        }
        timeout(
            Duration::from_secs(CMD_TIMEOUT_SECS),
            Command::new("cmd")
                .args(["/C", cmd])
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()?
                .wait_with_output(),
        )
        .await??
    };

    #[cfg(not(target_os = "windows"))]
    let out = {
        let (prog, args) = parse_safe_command(cmd)?;
        timeout(
            Duration::from_secs(CMD_TIMEOUT_SECS),
            Command::new(&prog)
                .args(&args)
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()?
                .wait_with_output(),
        )
        .await??
    };

    Ok(CommandResult {
        command_id: command_id.to_string(),
        output:     combine_output(&out.stdout, &out.stderr),
        exit_code:  out.status.code().unwrap_or(-1),
    })
}

// ── run_script ───────────────────────────────────────────────────────────────

async fn run_script(command_id: &str, script: &str) -> Result<CommandResult> {
    use tokio::fs;

    #[cfg(target_os = "windows")]
    let (tmp_path, interpreter, extra_args): (String, &str, Vec<&str>) = (
        format!(
            "{}\\rmm_{}.ps1",
            std::env::temp_dir().display(),
            uuid::Uuid::new_v4()
        ),
        "powershell",
        vec!["-ExecutionPolicy", "Bypass", "-File"],
    );

    #[cfg(not(target_os = "windows"))]
    let (tmp_path, interpreter, extra_args): (String, &str, Vec<&str>) = (
        format!("/tmp/rmm_{}.sh", uuid::Uuid::new_v4()),
        "bash",
        vec!["--restricted"],
    );

    fs::write(&tmp_path, script).await?;

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let meta = std::fs::metadata(&tmp_path)?;
        let mut perms = meta.permissions();
        perms.set_mode(0o700);
        std::fs::set_permissions(&tmp_path, perms)?;
    }

    let mut cmd_args = extra_args.clone();
    cmd_args.push(&tmp_path);

    let out = timeout(
        Duration::from_secs(CMD_TIMEOUT_SECS),
        Command::new(interpreter)
            .args(&cmd_args)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()?
            .wait_with_output(),
    )
    .await??;

    let _ = fs::remove_file(&tmp_path).await;

    Ok(CommandResult {
        command_id: command_id.to_string(),
        output:     combine_output(&out.stdout, &out.stderr),
        exit_code:  out.status.code().unwrap_or(-1),
    })
}

// ── kill_process ─────────────────────────────────────────────────────────────

async fn kill_process(command_id: &str, pid_str: &str) -> Result<CommandResult> {
    // Логируем что реально получили
    tracing::info!("kill_process called with pid_str='{pid_str}'");

    let pid: u32 = pid_str
        .trim()
        .parse()
        .map_err(|_| anyhow::anyhow!("Invalid PID: '{pid_str}'"))?;

    tracing::info!("Parsed PID: {pid}");

    if pid < 2 {
        bail!("Cannot kill PID < 2");
    }

    #[cfg(target_os = "windows")]
    let out = {
        tracing::info!("Running: taskkill /PID {pid} /F");
        Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/F"])
            .output()
            .await?
    };

    #[cfg(not(target_os = "windows"))]
    let out = Command::new("kill")
        .args(["-TERM", &pid.to_string()])
        .output()
        .await?;

    tracing::info!(
        "kill exit_code={:?} stdout={} stderr={}",
        out.status.code(),
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );

    Ok(CommandResult {
        command_id: command_id.to_string(),
        output:     combine_output(&out.stdout, &out.stderr),
        exit_code:  out.status.code().unwrap_or(-1),
    })
}


// ── get_process_list ─────────────────────────────────────────────────────────

async fn get_process_list(command_id: &str) -> Result<CommandResult> {
    let info = crate::sysinfo_collector::collect();
    Ok(CommandResult {
        command_id: command_id.to_string(),
        output:     serde_json::to_string(&info.processes)?,
        exit_code:  0,
    })
}

// ── service_cmd ──────────────────────────────────────────────────────────────
// Единственное определение — внутри используем cfg-блоки без return

async fn service_cmd(command_id: &str, action: &str) -> Result<CommandResult> {
    #[cfg(target_os = "windows")]
    let out = {
        let parts: Vec<&str> = action.splitn(2, ' ').collect();
        let sc_args: Vec<&str> = match parts.as_slice() {
            ["list"]        => vec!["query"],
            ["start", name] => vec!["start", name],
            ["stop",  name] => vec!["stop",  name],
            _ => bail!("Unknown service action: {action}"),
        };
        timeout(
            Duration::from_secs(30),
            Command::new("sc.exe")
                .args(&sc_args)
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()?
                .wait_with_output(),
        )
        .await??
    };

    #[cfg(not(target_os = "windows"))]
    let out = {
        let parts: Vec<&str> = action.split_whitespace().collect();
        if parts.is_empty() {
            bail!("Empty service command");
        }
        timeout(
            Duration::from_secs(30),
            Command::new("systemctl")
                .args(&parts)
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()?
                .wait_with_output(),
        )
        .await??
    };

    Ok(CommandResult {
        command_id: command_id.to_string(),
        output:     combine_output(&out.stdout, &out.stderr),
        exit_code:  out.status.code().unwrap_or(-1),
    })
}

// ── helpers ──────────────────────────────────────────────────────────────────

#[cfg(not(target_os = "windows"))]
fn parse_safe_command(cmd: &str) -> Result<(String, Vec<String>)> {
    let parts: Vec<String> = shell_words::split(cmd)
        .map_err(|e| anyhow::anyhow!("Invalid command syntax: {e}"))?;
    if parts.is_empty() {
        bail!("Empty command");
    }
    let blocked_bins = [
        "rm", "mkfs", "dd", "shred", "shutdown",
        "reboot", "init", "poweroff", "halt", "fdisk",
    ];
    let base = std::path::Path::new(&parts[0])
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or(&parts[0]);
    if blocked_bins.contains(&base) {
        bail!("Execution of '{base}' is blocked by policy");
    }
    Ok((parts[0].clone(), parts[1..].to_vec()))
}

fn combine_output(stdout: &[u8], stderr: &[u8]) -> String {
    let mut out = String::from_utf8_lossy(stdout).to_string();
    if !stderr.is_empty() {
        out.push_str("\n[stderr]\n");
        out.push_str(&String::from_utf8_lossy(stderr));
    }
    out.chars().take(65536).collect()
}

// ── tests ────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_echo_command() {
        let r = execute("t1", "shell", "echo hello").await.unwrap();
        assert_eq!(r.exit_code, 0);
        assert!(r.output.contains("hello"));
    }

    #[tokio::test]
    async fn test_invalid_pid() {
        let r = execute("t2", "process_kill", "abc").await;
        assert!(r.is_err());
    }

    #[tokio::test]
    async fn test_pid_too_small() {
        let r = execute("t3", "process_kill", "1").await;
        assert!(r.is_err());
    }

    #[cfg(not(target_os = "windows"))]
    #[test]
    fn test_blocked_binary() {
        let r = parse_safe_command("rm -rf /");
        assert!(r.is_err());
    }

    #[cfg(not(target_os = "windows"))]
    #[test]
    fn test_parse_command_ok() {
        let (prog, args) = parse_safe_command("ls -la /tmp").unwrap();
        assert_eq!(prog, "ls");
        assert_eq!(args, vec!["-la", "/tmp"]);
    }
}
