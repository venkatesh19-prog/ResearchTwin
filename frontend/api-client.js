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

        function getResearchers(params) {
            return request(withQuery("/researchers/", params), { auth: false });
        }

        function getSearchHistory(limit = 10) {
            return request(withQuery("/search-history", { limit }));
        }

        function recordSearch(query) {
            return request("/search-history", {
                method: "POST",
                body: { query },
            });
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

        function listMyCollaborationRequests(params) {
            return request(withQuery("/students/me/collaboration-requests", params));
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

        function listFacultyCollaborationRequests(status, params) {
            return request(withQuery("/faculty/me/collaboration-requests", {
                ...(status ? { status } : {}),
                ...(params || {})
            }));
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

        // --------------------------------------------------
        // RESEARCHTWIN 2.0
        // --------------------------------------------------

        function getMyVerification() {
            return request("/faculty/me/researcher-link/verification");
        }

        function submitMyVerification(payload) {
            return request("/faculty/me/researcher-link/verification", {
                method: "POST",
                body: payload,
            });
        }

        function listAdminVerifications(params) {
            return request(withQuery("/admin/verifications", params));
        }

        function decideVerification(verificationId, payload) {
            return request(
                `/admin/verifications/${encodeURIComponent(verificationId)}`,
                { method: "PUT", body: payload }
            );
        }

        function listResearcherVerifications(researcherId) {
            return request(
                `/admin/researchers/${encodeURIComponent(researcherId)}/verifications`
            );
        }

        function listMyWorkspaces() {
            return request("/workspaces/me");
        }

        function getWorkspace(workspaceId) {
            return request(`/workspaces/${encodeURIComponent(workspaceId)}`);
        }

        function listWorkspaceTasks(workspaceId) {
            return request(
                `/workspaces/${encodeURIComponent(workspaceId)}/tasks`
            );
        }

        function createWorkspaceTask(workspaceId, payload) {
            return request(
                `/workspaces/${encodeURIComponent(workspaceId)}/tasks`,
                { method: "POST", body: payload }
            );
        }

        function updateWorkspaceTask(workspaceId, taskId, payload) {
            return request(
                `/workspaces/${encodeURIComponent(workspaceId)}/tasks/${encodeURIComponent(taskId)}`,
                { method: "PUT", body: payload }
            );
        }

        function deleteWorkspaceTask(workspaceId, taskId) {
            return request(
                `/workspaces/${encodeURIComponent(workspaceId)}/tasks/${encodeURIComponent(taskId)}`,
                { method: "DELETE" }
            );
        }

        function listWorkspaceComments(workspaceId, params) {
            return request(
                withQuery(`/workspaces/${encodeURIComponent(workspaceId)}/comments`, params)
            );
        }

        function createWorkspaceComment(workspaceId, payload) {
            return request(
                `/workspaces/${encodeURIComponent(workspaceId)}/comments`,
                { method: "POST", body: payload }
            );
        }

        function deleteWorkspaceComment(workspaceId, commentId) {
            return request(
                `/workspaces/${encodeURIComponent(workspaceId)}/comments/${encodeURIComponent(commentId)}`,
                { method: "DELETE" }
            );
        }

        function listWorkspaceMilestones(workspaceId) {
            return request(
                `/workspaces/${encodeURIComponent(workspaceId)}/milestones`
            );
        }

        function createWorkspaceMilestone(workspaceId, payload) {
            return request(
                `/workspaces/${encodeURIComponent(workspaceId)}/milestones`,
                { method: "POST", body: payload }
            );
        }

        function updateWorkspaceMilestone(workspaceId, milestoneId, payload) {
            return request(
                `/workspaces/${encodeURIComponent(workspaceId)}/milestones/${encodeURIComponent(milestoneId)}`,
                { method: "PUT", body: payload }
            );
        }

        function deleteWorkspaceMilestone(workspaceId, milestoneId) {
            return request(
                `/workspaces/${encodeURIComponent(workspaceId)}/milestones/${encodeURIComponent(milestoneId)}`,
                { method: "DELETE" }
            );
        }

        function createTeam(payload) {
            return request("/teams", { method: "POST", body: payload });
        }

        function listMyTeams() {
            return request("/teams/me");
        }

        function getTeam(teamId) {
            return request(`/teams/${encodeURIComponent(teamId)}`);
        }

        function deleteTeam(teamId) {
            return request(`/teams/${encodeURIComponent(teamId)}`, {
                method: "DELETE",
            });
        }

        function inviteToTeam(teamId, payload) {
            return request(`/teams/${encodeURIComponent(teamId)}/invitations`, {
                method: "POST",
                body: payload,
            });
        }

        function decideTeamInvitation(teamId, invitationId, payload) {
            return request(
                `/teams/${encodeURIComponent(teamId)}/invitations/${encodeURIComponent(invitationId)}`,
                { method: "PUT", body: payload }
            );
        }

        function removeTeamMember(teamId, userId) {
            return request(
                `/teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(userId)}`,
                { method: "DELETE" }
            );
        }

        function getTeamRecommendations(teamId, payload) {
            return request(
                `/teams/${encodeURIComponent(teamId)}/recommendations`,
                { method: "POST", body: payload || {} }
            );
        }

        function searchOpportunities(params) {
            return request(withQuery("/opportunities", params));
        }

        function listMyOpportunities(params) {
            return request(withQuery("/opportunities/mine", params));
        }

        function createOpportunity(payload) {
            return request("/opportunities", { method: "POST", body: payload });
        }

        function getOpportunity(opportunityId) {
            return request(
                `/opportunities/${encodeURIComponent(opportunityId)}`
            );
        }

        function updateOpportunity(opportunityId, payload) {
            return request(
                `/opportunities/${encodeURIComponent(opportunityId)}`,
                { method: "PUT", body: payload }
            );
        }

        function deleteOpportunity(opportunityId) {
            return request(
                `/opportunities/${encodeURIComponent(opportunityId)}`,
                { method: "DELETE" }
            );
        }

        function getOpportunityEligibility(opportunityId) {
            return request(
                `/opportunities/${encodeURIComponent(opportunityId)}/eligibility`
            );
        }

        function matchOpportunities(payload) {
            return request("/students/me/opportunity-matches", {
                method: "POST",
                body: payload || {},
            });
        }

        function applyToOpportunity(opportunityId, payload) {
            return request(
                `/opportunities/${encodeURIComponent(opportunityId)}/applications`,
                { method: "POST", body: payload }
            );
        }

        function listMyApplications(params) {
            return request(
                withQuery("/students/me/opportunity-applications", params)
            );
        }

        function listOpportunityApplications(opportunityId, params) {
            return request(
                withQuery(
                    `/opportunities/${encodeURIComponent(opportunityId)}/applications`,
                    params
                )
            );
        }

        function decideOpportunityApplication(opportunityId, applicationId, payload) {
            return request(
                `/opportunities/${encodeURIComponent(opportunityId)}/applications/${encodeURIComponent(applicationId)}`,
                { method: "PUT", body: payload }
            );
        }

        function withdrawMyApplication(opportunityId) {
            return request(
                `/opportunities/${encodeURIComponent(opportunityId)}/applications/me`,
                { method: "DELETE" }
            );
        }

        function listOpportunitySources() {
            return request("/admin/opportunities/sources");
        }

        function importOpportunities(payload) {
            return request("/admin/opportunities/import", {
                method: "POST",
                body: payload,
            });
        }

        function getUniversityAnalytics() {
            return request("/analytics/university");
        }

        function getDepartmentAnalytics(params) {
            return request(withQuery("/analytics/departments", params));
        }

        function getResearchNetwork(params) {
            return request(
                withQuery("/research-intelligence/network", params)
            );
        }

        function getResearchClusters() {
            return request("/research-intelligence/clusters");
        }

        function rebuildResearchClusters(payload) {
            return request("/research-intelligence/clusters/rebuild", {
                method: "POST",
                body: payload || {},
            });
        }

        function predictTopics(payload) {
            return request("/research-intelligence/topics/predict", {
                method: "POST",
                body: payload,
            });
        }

        function getResearchTrends(params) {
            return request(
                withQuery("/research-intelligence/trends", params)
            );
        }

        function getKnowledgeGraph(params) {
            return request(
                withQuery("/research-intelligence/knowledge-graph", params)
            );
        }

        function listLiterature(params) {
            return request(withQuery("/literature", params));
        }

        function createLiteratureEntry(payload) {
            return request("/literature", { method: "POST", body: payload });
        }

        function getLiteratureEntry(entryId) {
            return request(`/literature/${encodeURIComponent(entryId)}`);
        }

        function updateLiteratureEntry(entryId, payload) {
            return request(`/literature/${encodeURIComponent(entryId)}`, {
                method: "PUT",
                body: payload,
            });
        }

        function deleteLiteratureEntry(entryId) {
            return request(`/literature/${encodeURIComponent(entryId)}`, {
                method: "DELETE",
            });
        }

        function listProposals(params) {
            return request(withQuery("/proposals", params));
        }

        function createProposal(payload) {
            return request("/proposals", { method: "POST", body: payload });
        }

        function getProposal(proposalId) {
            return request(`/proposals/${encodeURIComponent(proposalId)}`);
        }

        function updateProposal(proposalId, payload) {
            return request(`/proposals/${encodeURIComponent(proposalId)}`, {
                method: "PUT",
                body: payload,
            });
        }

        function deleteProposal(proposalId) {
            return request(`/proposals/${encodeURIComponent(proposalId)}`, {
                method: "DELETE",
            });
        }

        function addProposalCollaborator(proposalId, payload) {
            return request(
                `/proposals/${encodeURIComponent(proposalId)}/collaborators`,
                { method: "POST", body: payload }
            );
        }

        function removeProposalCollaborator(proposalId, userId) {
            return request(
                `/proposals/${encodeURIComponent(proposalId)}/collaborators/${encodeURIComponent(userId)}`,
                { method: "DELETE" }
            );
        }

        function addProposalSection(proposalId, payload) {
            return request(
                `/proposals/${encodeURIComponent(proposalId)}/sections`,
                { method: "POST", body: payload }
            );
        }

        function updateProposalSection(proposalId, sectionId, payload) {
            return request(
                `/proposals/${encodeURIComponent(proposalId)}/sections/${encodeURIComponent(sectionId)}`,
                { method: "PUT", body: payload }
            );
        }

        function deleteProposalSection(proposalId, sectionId) {
            return request(
                `/proposals/${encodeURIComponent(proposalId)}/sections/${encodeURIComponent(sectionId)}`,
                { method: "DELETE" }
            );
        }

        function addProposalCitation(proposalId, payload) {
            return request(
                `/proposals/${encodeURIComponent(proposalId)}/citations`,
                { method: "POST", body: payload }
            );
        }

        function deleteProposalCitation(proposalId, citationId) {
            return request(
                `/proposals/${encodeURIComponent(proposalId)}/citations/${encodeURIComponent(citationId)}`,
                { method: "DELETE" }
            );
        }

        function listProposalVersions(proposalId, params) {
            return request(
                withQuery(`/proposals/${encodeURIComponent(proposalId)}/versions`, params)
            );
        }

        function getProposalVersion(proposalId, version) {
            return request(
                `/proposals/${encodeURIComponent(proposalId)}/versions/${encodeURIComponent(version)}`
            );
        }

        function listTheses(params) {
            return request(withQuery("/theses", params));
        }

        function createThesis(payload) {
            return request("/theses", { method: "POST", body: payload });
        }

        function getThesis(thesisId) {
            return request(`/theses/${encodeURIComponent(thesisId)}`);
        }

        function updateThesis(thesisId, payload) {
            return request(`/theses/${encodeURIComponent(thesisId)}`, {
                method: "PUT",
                body: payload,
            });
        }

        function deleteThesis(thesisId) {
            return request(`/theses/${encodeURIComponent(thesisId)}`, {
                method: "DELETE",
            });
        }

        function addThesisMilestone(thesisId, payload) {
            return request(
                `/theses/${encodeURIComponent(thesisId)}/milestones`,
                { method: "POST", body: payload }
            );
        }

        function updateThesisMilestone(thesisId, milestoneId, payload) {
            return request(
                `/theses/${encodeURIComponent(thesisId)}/milestones/${encodeURIComponent(milestoneId)}`,
                { method: "PUT", body: payload }
            );
        }

        function deleteThesisMilestone(thesisId, milestoneId) {
            return request(
                `/theses/${encodeURIComponent(thesisId)}/milestones/${encodeURIComponent(milestoneId)}`,
                { method: "DELETE" }
            );
        }

        function getThesisHistory(thesisId, params) {
            return request(
                withQuery(`/theses/${encodeURIComponent(thesisId)}/history`, params)
            );
        }

        function listPublications(params) {
            return request(withQuery("/publication-submissions", params));
        }

        function createPublication(payload) {
            return request("/publication-submissions", {
                method: "POST",
                body: payload,
            });
        }

        function getPublication(submissionId, params) {
            return request(
                withQuery(
                    `/publication-submissions/${encodeURIComponent(submissionId)}`,
                    params
                )
            );
        }

        function updatePublication(submissionId, payload) {
            return request(
                `/publication-submissions/${encodeURIComponent(submissionId)}`,
                { method: "PUT", body: payload }
            );
        }

        function deletePublication(submissionId) {
            return request(
                `/publication-submissions/${encodeURIComponent(submissionId)}`,
                { method: "DELETE" }
            );
        }

        function updatePublicationStatus(submissionId, payload) {
            return request(
                `/publication-submissions/${encodeURIComponent(submissionId)}/status`,
                { method: "POST", body: payload }
            );
        }

        function addPublicationRevision(submissionId, payload) {
            return request(
                `/publication-submissions/${encodeURIComponent(submissionId)}/revisions`,
                { method: "POST", body: payload }
            );
        }

        function listLabs(params) {
            return request(withQuery("/labs", params));
        }

        function createLab(payload) {
            return request("/labs", { method: "POST", body: payload });
        }

        function getLab(labId) {
            return request(`/labs/${encodeURIComponent(labId)}`);
        }

        function updateLab(labId, payload) {
            return request(`/labs/${encodeURIComponent(labId)}`, {
                method: "PUT",
                body: payload,
            });
        }

        function deleteLab(labId) {
            return request(`/labs/${encodeURIComponent(labId)}`, {
                method: "DELETE",
            });
        }

        function listLabMembers(labId, params) {
            return request(
                withQuery(`/labs/${encodeURIComponent(labId)}/members`, params)
            );
        }

        function addLabMember(labId, payload) {
            return request(`/labs/${encodeURIComponent(labId)}/members`, {
                method: "POST",
                body: payload,
            });
        }

        function removeLabMember(labId, userId) {
            return request(
                `/labs/${encodeURIComponent(labId)}/members/${encodeURIComponent(userId)}`,
                { method: "DELETE" }
            );
        }

        function listCollaborations(params) {
            return request(
                withQuery("/interuniversity-collaborations", params)
            );
        }

        function createCollaboration(payload) {
            return request("/interuniversity-collaborations", {
                method: "POST",
                body: payload,
            });
        }

        function getCollaboration(collaborationId) {
            return request(
                `/interuniversity-collaborations/${encodeURIComponent(collaborationId)}`
            );
        }

        function updateCollaborationStatus(collaborationId, payload) {
            return request(
                `/interuniversity-collaborations/${encodeURIComponent(collaborationId)}/status`,
                { method: "POST", body: payload }
            );
        }

        function listInstitutions() {
            return request("/institutions", { auth: false });
        }

        function getMyInstitution() {
            return request("/institutions/me");
        }

        function createInstitution(payload) {
            return request("/admin/institutions", {
                method: "POST",
                body: payload,
            });
        }

        function renameInstitution(institutionId, payload) {
            return request(
                `/admin/institutions/${encodeURIComponent(institutionId)}`,
                { method: "PUT", body: payload }
            );
        }

        function listInstitutionMembers(institutionId) {
            return request(
                `/admin/institutions/${encodeURIComponent(institutionId)}/members`
            );
        }

        function assignInstitutionMember(institutionId, userId) {
            return request(
                `/admin/institutions/${encodeURIComponent(institutionId)}/members/${encodeURIComponent(userId)}`,
                { method: "PUT" }
            );
        }

        function removeInstitutionMember(institutionId, userId) {
            return request(
                `/admin/institutions/${encodeURIComponent(institutionId)}/members/${encodeURIComponent(userId)}`,
                { method: "DELETE" }
            );
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
            getSearchHistory,
            recordSearch,
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
            getMyVerification,
            submitMyVerification,
            listAdminVerifications,
            decideVerification,
            listResearcherVerifications,
            listMyWorkspaces,
            getWorkspace,
            listWorkspaceTasks,
            createWorkspaceTask,
            updateWorkspaceTask,
            deleteWorkspaceTask,
            listWorkspaceComments,
            createWorkspaceComment,
            deleteWorkspaceComment,
            listWorkspaceMilestones,
            createWorkspaceMilestone,
            updateWorkspaceMilestone,
            deleteWorkspaceMilestone,
            createTeam,
            listMyTeams,
            getTeam,
            deleteTeam,
            inviteToTeam,
            decideTeamInvitation,
            removeTeamMember,
            getTeamRecommendations,
            searchOpportunities,
            listMyOpportunities,
            createOpportunity,
            getOpportunity,
            updateOpportunity,
            deleteOpportunity,
            getOpportunityEligibility,
            matchOpportunities,
            applyToOpportunity,
            listMyApplications,
            listOpportunityApplications,
            decideOpportunityApplication,
            withdrawMyApplication,
            listOpportunitySources,
            importOpportunities,
            getUniversityAnalytics,
            getDepartmentAnalytics,
            getResearchNetwork,
            getResearchClusters,
            rebuildResearchClusters,
            predictTopics,
            getResearchTrends,
            getKnowledgeGraph,
            listLiterature,
            createLiteratureEntry,
            getLiteratureEntry,
            updateLiteratureEntry,
            deleteLiteratureEntry,
            listProposals,
            createProposal,
            getProposal,
            updateProposal,
            deleteProposal,
            addProposalCollaborator,
            removeProposalCollaborator,
            addProposalSection,
            updateProposalSection,
            deleteProposalSection,
            addProposalCitation,
            deleteProposalCitation,
            listProposalVersions,
            getProposalVersion,
            listTheses,
            createThesis,
            getThesis,
            updateThesis,
            deleteThesis,
            addThesisMilestone,
            updateThesisMilestone,
            deleteThesisMilestone,
            getThesisHistory,
            listPublications,
            createPublication,
            getPublication,
            updatePublication,
            deletePublication,
            updatePublicationStatus,
            addPublicationRevision,
            listLabs,
            createLab,
            getLab,
            updateLab,
            deleteLab,
            listLabMembers,
            addLabMember,
            removeLabMember,
            listCollaborations,
            createCollaboration,
            getCollaboration,
            updateCollaborationStatus,
            listInstitutions,
            getMyInstitution,
            createInstitution,
            renameInstitution,
            listInstitutionMembers,
            assignInstitutionMember,
            removeInstitutionMember,
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
