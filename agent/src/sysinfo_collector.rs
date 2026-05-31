use serde::{Deserialize, Serialize};
use sysinfo::{Disks, System};

#[derive(Debug, Serialize, Deserialize)]
pub struct SystemInfo {
    pub os_name: String,
    pub os_version: String,
    pub hostname: String,
    pub cpu_usage: f32,
    pub mem_total_mb: u64,
    pub mem_used_mb: u64,
    pub mem_usage: f32,
    pub disk_total_gb: f64,
    pub disk_free_gb: f64,
    pub uptime_secs: u64,
    pub processes: Vec<ProcessInfo>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ProcessInfo {
    pub pid: u32,
    pub name: String,
    pub cpu: f32,
    pub mem_mb: u64,
}

pub fn collect() -> SystemInfo {
    let mut sys = System::new_all();
    sys.refresh_all();

    let cpu = sys.global_cpu_info().cpu_usage();
    let mem_total = sys.total_memory() / 1024 / 1024;
    let mem_used = sys.used_memory() / 1024 / 1024;

    let disks = Disks::new_with_refreshed_list();
    let (disk_total, disk_free) = disks.iter().fold((0u64, 0u64), |(total, free), disk| {
        (total + disk.total_space(), free + disk.available_space())
    });

    let mut processes: Vec<ProcessInfo> = sys
        .processes()
        .values()
        .map(|process| ProcessInfo {
            pid: process.pid().as_u32(),
            name: process.name().chars().take(64).collect(),
            cpu: process.cpu_usage(),
            mem_mb: process.memory() / 1024 / 1024,
        })
        .collect();

    processes.sort_by(|a, b| b.mem_mb.cmp(&a.mem_mb));
    processes.truncate(50);

    SystemInfo {
        os_name: System::name().unwrap_or_default(),
        os_version: System::os_version().unwrap_or_default(),
        hostname: System::host_name().unwrap_or_default(),
        cpu_usage: cpu,
        mem_total_mb: mem_total,
        mem_used_mb: mem_used,
        mem_usage: if mem_total > 0 {
            mem_used as f32 / mem_total as f32 * 100.0
        } else {
            0.0
        },
        disk_total_gb: disk_total as f64 / 1e9,
        disk_free_gb: disk_free as f64 / 1e9,
        uptime_secs: System::uptime(),
        processes,
    }
}
