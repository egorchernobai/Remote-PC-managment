/**
 * Псевдо-терминал для отображения результатов команд.
 * Используется на странице agent_detail.html
 */
class Terminal {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.history   = [];
        this.historyIdx= -1;
        this._render();
    }

    _render() {
        this.container.innerHTML = `
        <div style="background:#000;border-radius:8px;overflow:hidden;
                    border:1px solid rgba(255,255,255,.08)">
            <div style="background:#1a1d27;padding:8px 12px;display:flex;
                        align-items:center;gap:8px">
                <span style="width:12px;height:12px;border-radius:50%;
                             background:#ef4444;display:inline-block"></span>
                <span style="width:12px;height:12px;border-radius:50%;
                             background:#f59e0b;display:inline-block"></span>
                <span style="width:12px;height:12px;border-radius:50%;
                             background:#22c55e;display:inline-block"></span>
                <span style="flex:1;text-align:center;color:#64748b;
                             font-size:12px">terminal</span>
                <button onclick="window._terminal.clear()"
                        style="background:none;color:#64748b;border:none;
                               cursor:pointer;font-size:12px">Clear</button>
            </div>
            <div id="terminal-output"
                 style="font-family:monospace;font-size:13px;padding:16px;
                        min-height:200px;max-height:400px;overflow-y:auto;
                        line-height:1.6;color:#e2e8f0"></div>
            <div style="display:flex;align-items:center;border-top:1px solid
                        rgba(255,255,255,.06);padding:8px 12px;gap:8px">
                <span style="color:#22c55e;font-family:monospace">$</span>
                <input id="terminal-input" type="text"
                       style="flex:1;background:none;border:none;
                              font-family:monospace;color:#e2e8f0;outline:none"
                       placeholder="Enter command..."
                       onkeydown="window._terminal.onKey(event)">
            </div>
        </div>`;
        window._terminal = this;
    }

    write(text, type = "output") {
        const el    = document.getElementById("terminal-output");
        const line  = document.createElement("div");
        const colors= {output:"#e2e8f0", error:"#ef4444",
                       info:"#6c63ff", success:"#22c55e", cmd:"#f59e0b"};
        line.style.color      = colors[type] || "#e2e8f0";
        line.style.whiteSpace = "pre-wrap";
        line.textContent      = text;
        el.appendChild(line);
        el.scrollTop = el.scrollHeight;
    }

    clear() {
        document.getElementById("terminal-output").innerHTML = "";
    }

    onKey(e) {
        const input = document.getElementById("terminal-input");
        if (e.key === "Enter") {
            const cmd = input.value.trim();
            if (!cmd) return;
            this.history.unshift(cmd);
            this.historyIdx = -1;
            this.write(`$ ${cmd}`, "cmd");
            input.value = "";
            this._dispatch(cmd);
        } else if (e.key === "ArrowUp") {
            this.historyIdx = Math.min(this.historyIdx+1, this.history.length-1);
            input.value = this.history[this.historyIdx] || "";
        } else if (e.key === "ArrowDown") {
            this.historyIdx = Math.max(this.historyIdx-1, -1);
            input.value = this.historyIdx >= 0 ? this.history[this.historyIdx] : "";
        }
    }

    async _dispatch(cmd) {
        // agentId должен быть доступен глобально
        if (typeof AGENT_ID === "undefined") {
            this.write("Error: AGENT_ID not defined", "error"); return;
        }
        this.write("⏳ Executing...", "info");
        const res = await apiFetch("/api/v1/commands/", {
            method: "POST",
            body: JSON.stringify({
                agent_id: AGENT_ID,
                command:  cmd,
                cmd_type: "shell"
            })
        });
        if (!res.ok) {
            const d = await res.json();
            this.write(`Error: ${d.error}`, "error"); return;
        }
        const {command_id} = await res.json();

        // Polling с таймаутом
        for (let i = 0; i < 30; i++) {
            await new Promise(r => setTimeout(r, 1500));
            const r2 = await apiFetch(`/api/v1/commands/${command_id}/result`);
            if (!r2.ok) continue;
            const d = await r2.json();
            if (d.status !== "pending" && d.status !== "running") {
                const type = d.exit_code === 0 ? "success" : "error";
                this.write(d.output || "(no output)", type);
                if (d.exit_code !== 0)
                    this.write(`Exit code: ${d.exit_code}`, "error");
                return;
            }
        }
        this.write("Timeout: no response from agent", "error");
    }
}
