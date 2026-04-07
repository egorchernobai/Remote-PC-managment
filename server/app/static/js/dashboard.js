/**
 * Глобальные утилиты: toast-уведомления, API хелперы, форматирование
 */

// ── Toast система ─────────────────────────────────────────────
(function initToasts() {
    const container = document.createElement("div");
    container.id = "toast-container";
    document.body.appendChild(container);
})();

function showToast(msg, type = "info", durationMs = 4000) {
    const t = document.createElement("div");
    t.className = `toast ${type}`;
    t.textContent = msg;
    document.getElementById("toast-container").appendChild(t);
    setTimeout(() => t.remove(), durationMs);
}

// ── Глобальный перехватчик ошибок fetch ───────────────────────
const _origApiFetch = window.apiFetch;
window.apiFetch = async function(url, options = {}) {
    try {
        const res = await _origApiFetch(url, options);
        if (!res.ok && res.status >= 500) {
            showToast(`Server error ${res.status}`, "error");
        }
        return res;
    } catch (err) {
        showToast(`Network error: ${err.message}`, "error");
        throw err;
    }
};

// ── Форматирование времени ─────────────────────────────────────
window.formatTime = function(t) {
    if (!t) return "Never";
    const d    = new Date(t);
    const diff = (Date.now() - d) / 1000;
    if (diff < 60)   return "just now";
    if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
    if (diff < 86400)return `${Math.floor(diff/3600)}h ago`;
    return d.toLocaleDateString("ru-RU");
};

// ── Копирование в буфер ────────────────────────────────────────
window.copyToClipboard = function(text) {
    navigator.clipboard.writeText(text)
        .then(() => showToast("Copied to clipboard", "success"))
        .catch(() => showToast("Copy failed", "error"));
};

// ── Экранирование HTML ─────────────────────────────────────────
window.escHtml = function(s) {
    return String(s)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;")
        .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
};
