(function (global) {
    "use strict";

    const TOKEN_KEY = "researchtwin.sessionToken";
    const DEFAULT_TIMEOUT_MS = 15000;
    const LOGIN_TIMEOUT_MS = 45000;
    const RECOMMENDATION_TIMEOUT_MS = 90000;

    class ApiError extends Error {
        constructor(message, { status = 0, kind = "api", detail = "" } = {}) {
            super(message);
            this.name = "ApiError";
            this.status = status;
            this.kind = kind;
            this.detail = detail;
        }
    }

    function readDetail(payload, fallback) {
        if (payload && typeof payload === "object") {
            if (typeof payload.detail === "string" && payload.detail.trim()) {
                return payload.detail;
            }
            if (Array.isArray(payload.detail)) {
                const messages = payload.detail
                    .map((entry) => (entry && entry.msg) || "")
                    .filter(Boolean);
                if (messages.length) return messages.join("; ");
            }
        }
        return fallback;
    }

    function resolveBaseUrl(options, global) {
        const raw = options.baseUrl ||
            (global && global.RESEARCHTWIN_API_BASE) ||
            "";
        if (!raw) return "";

        let parsed;
        try {
            parsed = new URL(String(raw).trim());
        } catch {
            return "";
        }

        if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return "";
        if (parsed.username || parsed.password) return "";
        if (parsed.search || parsed.hash) return "";
        if (parsed.pathname.replace(/\/+$/, "") !== "") return "";

        const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(parsed.hostname);
        if (parsed.protocol === "http:" && !loopback) return "";

        return parsed.origin;
    }

    function createApi(options = {}) {
        const baseUrl = resolveBaseUrl(options, global);

        let storage;
        try {
            storage = options.storage || (global && global.sessionStorage);
        } catch {
            storage = null;
        }
        const fetchImpl = options.fetchImpl ||
            (global && typeof global.fetch === "function" ? global.fetch.bind(global) : null);
        const timeoutOverride = options.timeoutMs;
        let unauthorizedHandler = options.onUnauthorized || null;
        let memoryToken = "";
        let sessionGeneration = 0;
        let authGeneration = 0;

        function getToken() {
            try {
                if (storage) memoryToken = storage.getItem(TOKEN_KEY) || "";
            } catch {
                storage = null;
            }
            return memoryToken;
        }

        function setToken(token) {
            memoryToken = token || "";
            sessionGeneration += 1;
            try {
                if (!storage) return;
                if (memoryToken) storage.setItem(TOKEN_KEY, memoryToken);
                else storage.removeItem(TOKEN_KEY);
            } catch {
                // Keep only the token in memory for this client. Stop reading
                // failed storage so an older persisted token cannot return.
                storage = null;
            }
        }

        function clearSession() {
            authGeneration += 1;
            setToken("");
        }

        function clearSessionIfCurrent(generation, token) {
            if (generation !== sessionGeneration || token !== getToken()) return false;
            // Response cleanup must not cancel a newer pending login/register.
            setToken("");
            return true;
        }

        function setUnauthorizedHandler(handler) {
            unauthorizedHandler = typeof handler === "function" ? handler : null;
        }

        async function request(path, requestOptions = {}) {
            const {
                method = "GET",
                body,
                auth = true,
                timeoutMs,
                notifyUnauthorized = true,
            } = requestOptions;

            if (!baseUrl) {
                throw new ApiError(
                    "The API endpoint is not configured for this deployment.",
                    { kind: "configuration" }
                );
            }

            if (typeof fetchImpl !== "function") {
                throw new ApiError("This browser cannot reach the API.", {
                    kind: "network",
                });
            }

            const timeout =
                timeoutMs ||
                timeoutOverride ||
                (path.includes("/recommendations")
                    ? RECOMMENDATION_TIMEOUT_MS
                    : DEFAULT_TIMEOUT_MS);

            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), timeout);
            const headers = {};

            if (body !== undefined) {
                headers["Content-Type"] = "application/json";
            }

            const generation = sessionGeneration;
            const token = getToken();
            if (auth && token) {
                headers.Authorization = `Bearer ${token}`;
            }

            let response;
            let text;
            try {
                response = await fetchImpl(`${baseUrl}${path}`, {
                    method,
                    headers,
                    body: body === undefined ? undefined : JSON.stringify(body),
                    signal: controller.signal,
                });
                text = await response.text();
            } catch (error) {
                if (controller.signal.aborted || (error && error.name === "AbortError")) {
                    throw new ApiError(
                        `Request timed out after ${Math.round(timeout / 1000)} seconds.`,
                        { kind: "timeout" }
                    );
                }
                throw new ApiError("Could not reach the API.", {
                    kind: "network",
                });
            } finally {
                clearTimeout(timer);
            }

            let payload = null;
            let validJson = false;
            try {
                payload = JSON.parse(text);
                validJson = true;
            } catch {
                // Preserve non-JSON HTTP error bodies for their useful details.
            }

            if (!response.ok) {
                const fallback = text.trim()
                    ? text.trim().slice(0, 200)
                    : `Request failed (${response.status}).`;
                const detail = readDetail(payload, fallback);

                if (response.status === 401 && auth && clearSessionIfCurrent(generation, token)) {
                    if (notifyUnauthorized && unauthorizedHandler) {
                        unauthorizedHandler(detail);
                    }
                }

                const kind =
                    response.status === 401
                        ? "unauthorized"
                        : response.status === 403
                            ? "forbidden"
                            : "http";

                throw new ApiError(detail || fallback, {
                    status: response.status,
                    kind,
                    detail,
                });
            }

            if (response.status === 204) return null;
            if (!validJson) {
                throw new ApiError("The API returned an invalid or empty JSON response.", {
                    status: response.status,
                    kind: "protocol",
                });
            }
            return payload;
        }

        async function authenticate(path, body, options = {}) {
            const generation = ++authGeneration;
            const data = await request(path, {
                method: "POST",
                body,
                auth: false,
                ...options,
            });
            if (generation !== authGeneration) {
                throw new ApiError(
                    "This authentication response is stale; a newer session action superseded it.",
                    { kind: "stale" }
                );
            }
            if (!data || !data.access_token) {
                throw new ApiError(
                    "The API did not return a session token.",
                    { kind: "protocol" }
                );
            }
            setToken(data.access_token);
            return data;
        }

        async function login(credentials) {
            return authenticate("/auth/login", credentials, {
                timeoutMs: LOGIN_TIMEOUT_MS,
            });
        }

        async function register(payload) {
            return authenticate("/auth/register", payload);
        }

        async function logout() {
            authGeneration += 1;
            const generation = sessionGeneration;
            const token = getToken();
            try {
                await request("/auth/logout", {
                    method: "POST",
                    notifyUnauthorized: false,
                });
            } finally {
                clearSessionIfCurrent(generation, token);
            }
        }

        function me() {
            return request("/auth/me");
        }

        function getStudentProfile() {
            return request("/students/me/profile");
        }

        function saveStudentProfile(profile) {
            return request("/students/me/profile", {
                method: "PUT",
                body: profile,
            });
        }

        function getRecommendations(topK = 5) {
            return request("/students/me/recommendations", {
                method: "POST",
                body: { top_k: topK },
            });
        }

        function getFacultyProfile() {
            return request("/faculty/me/profile");
        }

        function saveFacultyProfile(profile) {
            return request("/faculty/me/profile", {
                method: "PUT",
                body: profile,
            });
        }

        function getResearchers() {
            return request("/researchers/", { auth: false });
        }

        function getRoadmap(researcherId) {
            return request(`/students/me/researchers/${encodeURIComponent(researcherId)}/roadmap`);
        }

        function setRoadmapMilestone(researcherId, skill, milestoneIndex, completed) {
            return request(
                `/students/me/researchers/${encodeURIComponent(researcherId)}/roadmap/progress`,
                {
                    method: "PUT",
                    body: {
                        skill,
                        milestone_index: milestoneIndex,
                        completed
                    }
                }
            );
        }

        function createCollaborationRequest(researcherId, message) {
            return request("/students/me/collaboration-requests", {
                method: "POST",
                body: { researcher_id: researcherId, message }
            });
        }

        function listMyCollaborationRequests() {
            return request("/students/me/collaboration-requests");
        }

        function getFacultyResearcherLink() {
            return request("/faculty/me/researcher-link");
        }

        function setFacultyResearcherLink(researcherId) {
            return request("/faculty/me/researcher-link", {
                method: "PUT",
                body: { researcher_id: researcherId }
            });
        }

        function listFacultyCollaborationRequests(status) {
            const query = status ? `?status=${encodeURIComponent(status)}` : "";
            return request(`/faculty/me/collaboration-requests${query}`);
        }

        function decideCollaborationRequest(requestId, decision, response) {
            return request(
                `/faculty/me/collaboration-requests/${encodeURIComponent(requestId)}/decision`,
                {
                    method: "PUT",
                    body: { decision, response: response || "" }
                }
            );
        }

        function withQuery(path, filters) {
            const query = Object.entries(filters || {})
                .filter(([, value]) => value !== undefined && value !== null && value !== "")
                .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
                .join("&");
            return query ? `${path}?${query}` : path;
        }

        function listUsers(filters) {
            return request(withQuery("/admin/users", filters));
        }

        function setUserActive(userId, active) {
            return request(`/admin/users/${encodeURIComponent(userId)}/active`, {
                method: "PUT",
                body: { active },
            });
        }

        function setUserRole(userId, role) {
            return request(`/admin/users/${encodeURIComponent(userId)}/role`, {
                method: "PUT",
                body: { role },
            });
        }

        function revokeUserSessions(userId) {
            return request(`/admin/users/${encodeURIComponent(userId)}/sessions/revoke`, {
                method: "POST",
            });
        }

        function resetUserPassword(userId, password) {
            return request(`/admin/users/${encodeURIComponent(userId)}/password-reset`, {
                method: "POST",
                body: { password },
            });
        }

        function exportUserData(userId) {
            return request(`/admin/users/${encodeURIComponent(userId)}/data-export`);
        }

        function listAuditEvents(filters) {
            return request(withQuery("/admin/audit-events", filters));
        }

        function listGroups() {
            return request("/admin/groups");
        }

        function listGroupMembers(groupId) {
            return request(`/admin/groups/${encodeURIComponent(groupId)}/members`);
        }

        function addGroupMember(groupId, userId) {
            return request(`/admin/groups/${encodeURIComponent(groupId)}/members`, {
                method: "POST",
                body: { user_id: userId },
            });
        }

        function removeGroupMember(groupId, userId) {
            return request(
                `/admin/groups/${encodeURIComponent(groupId)}/members/${encodeURIComponent(userId)}`,
                { method: "DELETE" }
            );
        }

        function assignFacultyResearcherLink(facultyUserId, researcherId) {
            return request(`/admin/faculty/${encodeURIComponent(facultyUserId)}/researcher-link`, {
                method: "PUT",
                body: { researcher_id: researcherId },
            });
        }

        function removeFacultyResearcherLink(facultyUserId) {
            return request(`/admin/faculty/${encodeURIComponent(facultyUserId)}/researcher-link`, {
                method: "DELETE",
            });
        }

        return {
            baseUrl,
            login,
            register,
            logout,
            me,
            getStudentProfile,
            saveStudentProfile,
            getRecommendations,
            getFacultyProfile,
            saveFacultyProfile,
            getResearchers,
            getRoadmap,
            setRoadmapMilestone,
            createCollaborationRequest,
            listMyCollaborationRequests,
            getFacultyResearcherLink,
            setFacultyResearcherLink,
            listFacultyCollaborationRequests,
            decideCollaborationRequest,
            listUsers,
            setUserActive,
            setUserRole,
            revokeUserSessions,
            resetUserPassword,
            exportUserData,
            listAuditEvents,
            listGroups,
            listGroupMembers,
            addGroupMember,
            removeGroupMember,
            assignFacultyResearcherLink,
            removeFacultyResearcherLink,
            clearSession,
            hasSession: () => Boolean(getToken()),
            setUnauthorizedHandler,
        };
    }

    const exported = { createApi, ApiError, TOKEN_KEY };

    if (typeof module !== "undefined" && module.exports) {
        module.exports = exported;
    }

    if (global) {
        global.ResearchTwinAPI = createApi();
    }
})(typeof window !== "undefined" ? window : globalThis);
