(function () {
    "use strict";

    var LOCAL_HOSTS = ["localhost", "127.0.0.1", "[::1]"];
    var LOCAL_API_BASE = "http://127.0.0.1:8000";
    var PRODUCTION_HOSTS = ["starlit-empanada-a323e3.netlify.app"];
    var PRODUCTION_API_BASE = "https://researchtwin-api.onrender.com";

    if (window.RESEARCHTWIN_API_BASE) {
        return;
    }

    var hostname = String(
        (window.location && window.location.hostname) || ""
    ).toLowerCase();

    if (LOCAL_HOSTS.indexOf(hostname) !== -1) {
        window.RESEARCHTWIN_API_BASE = LOCAL_API_BASE;
    } else if (PRODUCTION_HOSTS.indexOf(hostname) !== -1) {
        window.RESEARCHTWIN_API_BASE = PRODUCTION_API_BASE;
    }
    // Any other host stays unset; api-client.js then fails closed instead of
    // sending credentials to a backend this deployment was not configured for.
}());
