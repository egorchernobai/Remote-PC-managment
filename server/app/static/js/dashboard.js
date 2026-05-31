(function initToasts() {
    const container = document.createElement("div");
    container.id = "toast-container";
    document.body.appendChild(container);
})();

function showToast(message, type = "info", durationMs = 4000) {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.getElementById("toast-container").appendChild(toast);
    setTimeout(() => toast.remove(), durationMs);
}

const originalApiFetch = window.apiFetch;
window.apiFetch = async function(url, options = {}) {
    try {
        const response = await originalApiFetch(url, options);
        if (!response.ok && response.status >= 500) {
            showToast(`Server error ${response.status}`, "error");
        }
        return response;
    } catch (err) {
        showToast(`Network error: ${err.message}`, "error");
        throw err;
    }
};

window.formatTime = function(value) {
    if (!value) return "Never";
    const date = new Date(value);
    const diffSeconds = (Date.now() - date) / 1000;
    if (diffSeconds < 60) return "just now";
    if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
    if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`;
    return date.toLocaleDateString("ru-RU");
};

window.copyToClipboard = function(text) {
    navigator.clipboard.writeText(text)
        .then(() => showToast("Copied to clipboard", "success"))
        .catch(() => showToast("Copy failed", "error"));
};

window.escHtml = function(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
};
