window.RESEARCHTWIN_API_BASE = window.RESEARCHTWIN_API_BASE ||
    (["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname)
        ? "http://127.0.0.1:8000"
        : "https://researchtwin-api.onrender.com");

