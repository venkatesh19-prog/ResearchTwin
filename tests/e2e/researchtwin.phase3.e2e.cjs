/* Phase 3 end-to-end verification using the real browser and API. */

const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { randomUUID } = require("node:crypto");
const { chromium, request } = require("playwright");

const FRONTEND_URL = (process.env.RT_PHASE3_FRONTEND_URL || "http://127.0.0.1:5500").replace(/\/$/, "");
const API_URL = (process.env.RT_PHASE3_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const DATABASE_URL = process.env.RT_PHASE3_DATABASE_URL || "";
const PYTHON = process.env.RT_PHASE3_PYTHON || "python";
const ARTIFACT_DIR = process.env.RT_PHASE3_ARTIFACT_DIR || path.join(os.tmpdir(), "researchtwin-phase3-artifacts");
const PASSWORD = "ResearchTwin E2E Password 2026!";
const RESET_PASSWORD = "ResearchTwin Reset Password 2026!";
const ADMIN_EMAIL = process.env.RT_PHASE3_ADMIN_EMAIL || "";
const ADMIN_PASSWORD = process.env.RT_PHASE3_ADMIN_PASSWORD || "";
const ID = randomUUID().slice(0, 12);

function assertTemporaryDatabase(url) {
    assert.ok(url.startsWith("sqlite:///"), "E2E_DATABASE_URL must explicitly select SQLite");
    const lower = url.toLowerCase().replace(/\\/g, "/");
    assert.ok(lower.includes("/temp/") || lower.includes("/tmp/"),
        "E2E_DATABASE_URL must point inside the operating system temp directory");
}

async function expectVisible(locator, timeout = 20000) {
    await locator.waitFor({ state: "visible", timeout });
}

async function openAuth(page) {
    const response = await page.goto(`${FRONTEND_URL}/researchtwin.html`);
    assert.equal(response.status(), 200, "frontend route should load over HTTP");
    await expectVisible(page.locator("#authShell"));
}

async function register(page, { name, email, role }) {
    await openAuth(page);
    await page.locator("#tabRegister").click();
    await page.locator("#regName").fill(name);
    await page.locator("#regEmail").fill(email);
    await page.locator("#regPassword").fill(PASSWORD);
    await page.locator("#regRole").selectOption(role);
    await page.locator("#registerBtn").click();
    await expectVisible(page.locator("#appSidebar:not(.hidden)"), 30000);
    assert.match(await page.locator("#userChip").innerText(), new RegExp(email, "i"));
}

async function signOut(page) {
    await page.locator("#logoutBtn").click();
    await expectVisible(page.locator("#authShell:not(.hidden)"), 20000);
    await page.waitForFunction(() => !sessionStorage.getItem("researchtwin.sessionToken"));
}

async function signIn(page, email) {
    return signInWithPassword(page, email, PASSWORD);
}

async function signInWithPassword(page, email, password) {
    await expectVisible(page.locator("#authShell:not(.hidden)"));
    await page.locator("#tabLogin").click();
    await page.locator("#loginEmail").fill(email);
    await page.locator("#loginPassword").fill(password);
    await page.locator("#loginBtn").click();
    await expectVisible(page.locator("#appSidebar:not(.hidden)"), 30000);
}

async function saveStudentProfile(page) {
    await page.locator('#navMenu a[data-view="studentView"]').click();
    await page.locator("#sAreas").waitFor({ state: "visible" });
    await page.locator("#sAreas").fill("Artificial Intelligence, Machine Learning");
    await page.locator("#sExpertise").fill("Deep Learning, Natural Language Processing");
    await page.locator("#sSkills").fill("Python");
    await page.locator("#sCourses").fill("Algorithms, Statistics");
    await page.locator("#sProjects").fill("An AI research matching prototype");
    await page.locator("#sPublications").fill("NLP and machine learning studies");
    await page.locator("#sAcademic").fill("MSc Computer Science, research experience");
    await page.locator("#saveStudentBtn").click();
    await page.waitForFunction(() => /saved to the database/i.test(document.querySelector("#studentStatus")?.innerText || ""), { timeout: 30000 });
}

async function getRecommendations(page) {
    await page.locator('#navMenu a[data-view="matchView"]').click();
    await page.waitForFunction(() => {
        const button = document.querySelector("#refreshMatchesBtn");
        return button && !button.disabled;
    }, undefined, { timeout: 120000 });
    const availableCounts = await page.locator("#recommendationCount option").evaluateAll(options =>
        options.map(option => Number(option.value))
    );
    assert.ok(availableCounts.every(count => count >= 1 && count <= 10),
        "the frontend must not offer a count rejected by the API");
    await page.locator("#recommendationCount").selectOption("10");
    const responsePromise = page.waitForResponse(response =>
        response.url().endsWith("/students/me/recommendations") &&
        response.request().method() === "POST", { timeout: 120000 });
    await page.locator("#refreshMatchesBtn").click();
    const response = await responsePromise;
    assert.equal(response.status(), 200, `recommendation response failed: ${await response.text()}`);
    const data = await response.json();
    assert.ok(Array.isArray(data.recommendations) && data.recommendations.length > 0,
        "saved profile should produce at least one recommendation");

    const scores = data.recommendations.map(item => item.match_score);
    assert.ok(scores.every(Number.isFinite), "all recommendation scores should be finite");
    assert.deepEqual(scores, [...scores].sort((a, b) => b - a),
        "recommendations should be ranked by descending score");

    const features = [
        "tfidf_similarity", "semantic_similarity", "research_area_similarity",
        "expertise_similarity", "skill_overlap", "project_similarity",
        "publication_similarity",
    ];
    for (const item of data.recommendations) {
        assert.deepEqual(Object.keys(item.component_scores), features,
            "serving feature order should match the seven-feature artifact");
        assert.equal(item.explanation.all_contributions.length, features.length);
        assert.deepEqual(new Set(item.explanation.all_contributions.map(row => row.feature)), new Set(features),
            "SHAP explanation should cover exactly the features used by the model");
        assert.ok(item.explanation.all_contributions.every(row =>
            Number.isFinite(row.shap_value) && Number.isFinite(row.feature_value)));
        for (const contribution of item.explanation.all_contributions) {
            assert.ok(Math.abs(contribution.feature_value - item.component_scores[contribution.feature]) <= 0.000051,
                `explanation value should match the served ${contribution.feature} component`);
        }
    }
    await page.locator("#matchesContainer .match-card").first().waitFor({ state: "attached", timeout: 30000 });
    return data.recommendations;
}

async function requestCollaboration(page, researcherId, message) {
    await page.locator('#navMenu a[data-view="matchView"]').click();
    const slot = page.locator(`#request-${researcherId}`);
    await page.locator(`#matchesContainer .match-card button[onclick="toggleRequestForm(${researcherId})"]`).click();
    await slot.locator("textarea").fill(message);
    await slot.getByRole("button", { name: "Send request" }).click();
    await slot.locator(".request-item").waitFor({ state: "attached", timeout: 30000 });
}

async function requestJson(api, method, url, options = {}) {
    const response = await api[method](url, options);
    return { response, body: await response.json().catch(() => ({})) };
}

async function expireUserSessions(email) {
    const python = [
        "import time",
        "from app.database import SessionLocal",
        "from app.models import AuthSession, User",
        "db = SessionLocal()",
        "try:",
        `    user = db.query(User).filter(User.email == ${JSON.stringify(email)}).one()`,
        "    count = db.query(AuthSession).filter(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)).update({AuthSession.expires_at: int(time.time()) - 1})",
        "    db.commit()",
        "    assert count > 0",
        "finally:",
        "    db.close()",
    ].join("\n");
    execFileSync(PYTHON, ["-c", python], {
        cwd: path.resolve(__dirname, "../../backend"),
        env: { ...process.env, DATABASE_URL },
        stdio: "pipe",
    });
}

async function main() {
    assertTemporaryDatabase(DATABASE_URL);
    assert.ok(ADMIN_EMAIL && ADMIN_PASSWORD,
        "set RT_PHASE3_ADMIN_EMAIL/PASSWORD for the temporary CLI-provisioned admin");
    fs.mkdirSync(ARTIFACT_DIR, { recursive: true });

    const journeyResults = [];
    const consoleErrors = [];
    const pageErrors = [];
    const failedRequests = [];
    const httpErrors = [];
    let expectedNetworkFailure = false;
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1050 } });
    await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
    const recordPage = page => {
        page.on("console", message => {
            if (message.type() === "error") consoleErrors.push(message.text());
        });
        page.on("pageerror", error => pageErrors.push(error.message));
        page.on("requestfailed", request => {
            failedRequests.push({ url: request.url(), error: request.failure()?.errorText || "unknown" });
        });
        page.on("response", response => {
            if (response.status() >= 400) {
                httpErrors.push({ status: response.status(), url: response.url() });
            }
        });
    };

    const api = await request.newContext({ baseURL: API_URL, timeout: 30000 });
    let failed = true;
    try {
        const health = await api.get("/health");
        assert.equal(health.status(), 200);
        assert.equal((await health.json()).status, "healthy");
        const ready = await api.get("/ready");
        assert.equal(ready.status(), 200);
        assert.equal((await ready.json()).status, "ready");

        const adminLogin = await requestJson(api, "post", "/auth/login", {
            data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
        });
        assert.equal(adminLogin.response.status(), 200, "temporary admin CLI login should work");
        const adminHeaders = { Authorization: `Bearer ${adminLogin.body.access_token}` };
        const adminMe = await api.get("/auth/me", { headers: adminHeaders });
        assert.equal(adminMe.status(), 200);
        assert.equal((await adminMe.json()).role, "admin");

        const anonymousImport = await api.post("/researchers/import");
        assert.equal(anonymousImport.status(), 401);
        const directoryBeforeImport = await api.get("/researchers/");
        assert.equal(directoryBeforeImport.status(), 200);
        const wasEmpty = (await directoryBeforeImport.json()).length === 0;
        const firstImport = await requestJson(api, "post", "/researchers/import", { headers: adminHeaders });
        assert.equal(firstImport.response.status(), 200);
        if (wasEmpty) {
            assert.ok(firstImport.body.imported_count > 0, "admin import should add the bundled directory");
        } else {
            assert.equal(firstImport.body.imported_count, 0, "existing directory records should not be duplicated");
        }
        const directoryAfterImport = await api.get("/researchers/");
        assert.equal(directoryAfterImport.status(), 200);
        assert.ok((await directoryAfterImport.json()).length > 0, "researcher directory should be available after import");
        const repeatImport = await requestJson(api, "post", "/researchers/import", { headers: adminHeaders });
        assert.equal(repeatImport.response.status(), 200);
        assert.equal(repeatImport.body.imported_count, 0, "repeated import should be idempotent");
        journeyResults.push("isolated admin provisioning, authorization, and duplicate-safe import");

        const student1 = {
            name: `E2E Student One ${ID}`,
            email: `e2e-student-one-${ID}@example.test`,
            role: "student",
        };
        const student2 = {
            name: `E2E Student Two ${ID}`,
            email: `e2e-student-two-${ID}@example.test`,
            role: "student",
        };
        const faculty = {
            name: `E2E Faculty ${ID}`,
            email: `e2e-faculty-${ID}@example.test`,
            role: "faculty",
        };

        // Invalid input is rejected before a request is sent.
        const invalidPage = await context.newPage();
        recordPage(invalidPage);
        await openAuth(invalidPage);
        await invalidPage.locator("#tabRegister").click();
        await invalidPage.locator("#regName").fill("Invalid E2E");
        await invalidPage.locator("#regEmail").fill(`invalid-${ID}@example.test`);
        await invalidPage.locator("#regPassword").fill("short");
        await invalidPage.locator("#registerBtn").click();
        assert.match(await invalidPage.locator("#registerError").innerText(), /at least 8 characters/i);
        await invalidPage.close();
        journeyResults.push("invalid registration input handling");

        // Registration, logout/login, session restore, and the empty profile state.
        const studentPage = await context.newPage();
        recordPage(studentPage);
        await register(studentPage, student1);
        const emptyProfileToken = await studentPage.evaluate(() => sessionStorage.getItem("researchtwin.sessionToken"));
        const emptyProfileRecommendations = await api.post("/students/me/recommendations", {
            headers: { Authorization: `Bearer ${emptyProfileToken}` },
            data: { top_k: 5 },
        });
        assert.equal(emptyProfileRecommendations.status(), 400,
            "recommendations should require a saved student profile");
        await expectVisible(studentPage.locator("#matchesContainer button"));
        assert.match(
            await studentPage.locator("#matchesContainer").innerText(),
            /save your student profile|no research interests|add some details/i
        );
        await signOut(studentPage);
        await signIn(studentPage, student1.email);
        await studentPage.reload();
        await expectVisible(studentPage.locator("#appSidebar:not(.hidden)"), 30000);
        assert.match(await studentPage.locator("#userChip").innerText(), new RegExp(student1.email, "i"));
        await saveStudentProfile(studentPage);
        await saveStudentProfile(studentPage); // Exercise editing and persistence, not just first creation.
        journeyResults.push("student register/login, session restore, profile create/edit, and safe empty-profile rejection");

        // Login failure/network failure is rendered in the browser without a script exception.
        const networkPage = await context.newPage();
        recordPage(networkPage);
        await openAuth(networkPage);
        await networkPage.locator("#tabRegister").click();
        await networkPage.locator("#regName").fill("Network Failure Check");
        await networkPage.locator("#regEmail").fill(`network-${ID}@example.test`);
        await networkPage.locator("#regPassword").fill(PASSWORD);
        await networkPage.route(`${API_URL}/auth/register`, route => {
            expectedNetworkFailure = true;
            return route.abort();
        });
        await networkPage.locator("#registerBtn").click();
        await networkPage.locator("#registerError").waitFor({ state: "visible" });
        await networkPage.waitForFunction(() => Boolean(document.querySelector("#registerError")?.innerText.trim()));
        assert.ok((await networkPage.locator("#registerError").innerText()).length > 0);
        await networkPage.close();
        journeyResults.push("browser network failure handling");

        // Admin authorization rejects both user roles.
        const studentToken = await studentPage.evaluate(() => sessionStorage.getItem("researchtwin.sessionToken"));
        assert.ok(studentToken);
        const studentAdminAttempt = await api.post("/researchers/import", {
            headers: { Authorization: `Bearer ${studentToken}` },
        });
        assert.equal(studentAdminAttempt.status(), 403);
        const studentCreateAttempt = await api.post("/researchers/", {
            headers: { Authorization: `Bearer ${studentToken}` },
            data: { name: "Unauthorized Browser Attempt" },
        });
        assert.equal(studentCreateAttempt.status(), 403);

        // Run the real model and validate finite scores, ranking, feature order, and SHAP coverage.
        const recommendations = await getRecommendations(studentPage);
        const selected = recommendations.find(item => Array.isArray(item.skill_gap) && item.skill_gap.length > 0);
        assert.ok(selected, "at least one recommendation should have a roadmap skill gap");
        const researcherId = selected.researcher_id;
        const researcherName = selected.name;
        journeyResults.push(`real seven-feature recommendation/model explanations (${recommendations.length} ranked results)`);

        // Open the corresponding directory record and its expandable profile details.
        await studentPage.locator('#navMenu a[data-view="directoryView"]').click();
        await studentPage.locator("#facSearch").fill(researcherName);
        await studentPage.locator("#facultyList").getByText(researcherName, { exact: false }).first().waitFor({ state: "visible" });
        const details = studentPage.locator("#facultyList details").first();
        await details.locator("summary").click();
        assert.ok(await details.getAttribute("open") !== null, "researcher profile details should open");
        await studentPage.locator('#navMenu a[data-view="matchView"]').click();
        journeyResults.push("researcher directory profile details");

        // A delayed roadmap GET must not repaint a view after the page refreshes.
        const roadmapPattern = `${API_URL}/students/me/researchers/${researcherId}/roadmap`;
        let roadmapFetched;
        const roadmapReady = new Promise(resolve => { roadmapFetched = resolve; });
        await studentPage.route(roadmapPattern, async route => {
            try {
                const response = await route.fetch();
                roadmapFetched();
                await new Promise(resolve => setTimeout(resolve, 1200));
                await route.fulfill({ response });
            } catch {
                roadmapFetched(); // A navigation may cancel the old document's route.
            }
        });
        await studentPage.locator(`#matchesContainer .match-card button[onclick="toggleRoadmap(${researcherId})"]`).click();
        await roadmapReady;
        await studentPage.reload();
        await expectVisible(studentPage.locator("#appSidebar:not(.hidden)"), 30000);
        await studentPage.unroute(roadmapPattern);
        await studentPage.locator("#matchesContainer .match-card").first().waitFor({ state: "attached", timeout: 120000 });
        assert.notEqual(await studentPage.locator(`#roadmap-${researcherId}`).getAttribute("data-open"), "1",
            "a delayed roadmap read should not reopen a panel after page refresh");
        journeyResults.push("refresh during delayed roadmap request");

        // Roadmap persistence and conflict protection for simultaneous milestone clicks.
        const roadmapButton = studentPage.locator(`#matchesContainer .match-card button[onclick="toggleRoadmap(${researcherId})"]`);
        await roadmapButton.click();
        const roadmapSlot = studentPage.locator(`#roadmap-${researcherId}`);
        await roadmapSlot.getByText("Roadmap for", { exact: false }).waitFor({ state: "visible", timeout: 30000 });
        const checkboxes = roadmapSlot.locator('input[type="checkbox"]');
        assert.ok(await checkboxes.count() >= 2, "roadmap should expose multiple milestones");

        let progressFetched;
        const progressReady = new Promise(resolve => { progressFetched = resolve; });
        let releaseProgress;
        const progressGate = new Promise(resolve => { releaseProgress = resolve; });
        const progressPattern = `${API_URL}/students/me/researchers/${researcherId}/roadmap/progress`;
        let progressRequestCount = 0;
        await studentPage.route(progressPattern, async route => {
            progressRequestCount += 1;
            try {
                const response = await route.fetch();
                progressFetched();
                await progressGate;
                await route.fulfill({ response });
            } catch {
                progressFetched();
            }
        });
        await checkboxes.first().check();
        await progressReady;
        assert.ok(await checkboxes.nth(0).isDisabled());
        assert.ok(await checkboxes.nth(1).isDisabled(), "concurrent milestone controls should lock together");
        releaseProgress();
        await studentPage.unroute(progressPattern);
        await studentPage.waitForFunction(id => {
            const input = document.querySelector(`#roadmap-${id} input[type="checkbox"]`);
            return input && input.checked && !input.disabled;
        }, researcherId, { timeout: 30000 });
        assert.equal(progressRequestCount, 1, "only one milestone update should reach the API");

        // The write has committed server-side; a browser refresh must restore it from the database.
        await studentPage.reload();
        await expectVisible(studentPage.locator("#appSidebar:not(.hidden)"), 30000);
        await studentPage.locator("#matchesContainer .match-card").first().waitFor({ state: "attached", timeout: 120000 });
        await studentPage.locator(`#matchesContainer .match-card button[onclick="toggleRoadmap(${researcherId})"]`).click();
        const reopenedRoadmap = studentPage.locator(`#roadmap-${researcherId}`);
        await reopenedRoadmap.getByText("Roadmap for", { exact: false }).waitFor({ state: "visible", timeout: 30000 });
        assert.equal(await reopenedRoadmap.locator('input[type="checkbox"]').first().isChecked(), true,
            "completed milestone should persist after refresh");
        journeyResults.push("roadmap generation, concurrent milestone lock, and persisted completion after refresh");

        // Create a pending request from the student UI, then verify duplicate rejection.
        const message1 = `Collaboration request one ${ID}`;
        await requestCollaboration(studentPage, researcherId, message1);
        const duplicateSlot = studentPage.locator(`#request-${researcherId}`);
        await studentPage.locator(`#matchesContainer .match-card button[onclick="toggleRequestForm(${researcherId})"]`).click();
        await duplicateSlot.locator("textarea").fill(`Duplicate ${ID}`);
        await duplicateSlot.getByRole("button", { name: "Send request" }).click();
        await duplicateSlot.locator(".status-text.error").waitFor({ state: "visible" });
        assert.match(await duplicateSlot.locator(".status-text").innerText(), /already have a pending request/i);
        await studentPage.locator('#navMenu a[data-view="requestsView"]').click();
        await studentPage.locator("#requestsList .status-pending").waitFor({ state: "visible" });
        journeyResults.push("collaboration request creation, duplicate rejection, and student-visible pending status");

        // Second student creates a different request to exercise faculty accept/reject.
        const secondPage = await context.newPage();
        recordPage(secondPage);
        await register(secondPage, student2);
        await saveStudentProfile(secondPage);
        const secondRecommendations = await getRecommendations(secondPage);
        assert.ok(secondRecommendations.some(item => item.researcher_id === researcherId),
            "the shared test researcher should be present for the second student");
        await requestCollaboration(secondPage, researcherId, `Collaboration request two ${ID}`);
        const secondToken = await secondPage.evaluate(() => sessionStorage.getItem("researchtwin.sessionToken"));
        const secondStudentAdminAttempt = await api.post("/researchers/import", {
            headers: { Authorization: `Bearer ${secondToken}` },
        });
        assert.equal(secondStudentAdminAttempt.status(), 403);

        // Faculty registration/profile editing and the pre-verification link state.
        const facultyPage = await context.newPage();
        recordPage(facultyPage);
        await register(facultyPage, faculty);
        await signOut(facultyPage);
        await signIn(facultyPage, faculty.email);
        await facultyPage.reload();
        await expectVisible(facultyPage.locator("#appSidebar:not(.hidden)"), 30000);
        await facultyPage.locator("#fDepartment").fill("Computer Science and Engineering");
        await facultyPage.locator("#fDesignation").fill("Associate Professor");
        await facultyPage.locator("#fAreas").fill("Artificial Intelligence, Machine Learning");
        await facultyPage.locator("#fExpertise").fill("Deep Learning");
        await facultyPage.locator("#fSkills").fill("Python, PyTorch");
        await facultyPage.locator("#fPublications").fill("E2E faculty profile publication");
        await facultyPage.locator("#fProjects").fill("E2E faculty project");
        await facultyPage.locator("#saveFacultyBtn").click();
        await facultyPage.waitForFunction(() => /profile saved/i.test(document.querySelector("#facultyStatus")?.innerText || ""), { timeout: 30000 });
        await facultyPage.waitForFunction(() => !document.querySelector("#saveFacultyBtn")?.disabled);
        await facultyPage.locator("#fDesignation").fill("Professor");
        await facultyPage.locator("#saveFacultyBtn").click();
        await facultyPage.waitForFunction(() => /profile saved/i.test(document.querySelector("#facultyStatus")?.innerText || ""), { timeout: 30000 });
        await facultyPage.locator('#navMenu a[data-view="inboxView"]').click();
        await facultyPage.locator("#linkPanel").getByText(/not linked/i).waitFor({ state: "visible" });

        const facultyToken = await facultyPage.evaluate(() => sessionStorage.getItem("researchtwin.sessionToken"));
        const facultyMe = await api.get("/auth/me", { headers: { Authorization: `Bearer ${facultyToken}` } });
        assert.equal(facultyMe.status(), 200);
        const facultyUser = await facultyMe.json();
        assert.equal(facultyUser.role, "faculty");
        const facultyImportAttempt = await api.post("/researchers/import", {
            headers: { Authorization: `Bearer ${facultyToken}` },
        });
        assert.equal(facultyImportAttempt.status(), 403);
        const unverifiedLinkAttempt = await api.put("/faculty/me/researcher-link", {
            headers: { Authorization: `Bearer ${facultyToken}` },
            data: { researcher_id: researcherId },
        });
        assert.equal(unverifiedLinkAttempt.status(), 403);
        const linked = await api.put(`/admin/faculty/${facultyUser.id}/researcher-link`, {
            headers: adminHeaders,
            data: { researcher_id: researcherId },
        });
        assert.equal(linked.status(), 200);
        assert.equal((await linked.json()).researcher.id, researcherId);
        await facultyPage.locator("#refreshInboxBtn").click();
        await facultyPage.locator("#linkResults").getByText(researcherName, { exact: false }).waitFor({ state: "visible" });
        await facultyPage.locator("#inboxList").getByText(student1.name, { exact: false }).waitFor({ state: "visible" });
        await facultyPage.locator("#inboxList").getByText(student2.name, { exact: false }).waitFor({ state: "visible" });

        // Accept one request and reject the other through the faculty UI.
        let requestItem = facultyPage.locator("#inboxList .request-item").filter({ hasText: student1.name });
        await requestItem.getByRole("button", { name: "Accept" }).click();
        requestItem = facultyPage.locator("#inboxList .request-item").filter({ hasText: student1.name });
        await requestItem.getByText("accepted", { exact: true }).waitFor({ state: "visible" });
        assert.equal(await requestItem.getByRole("button", { name: "Accept" }).count(), 0);

        requestItem = facultyPage.locator("#inboxList .request-item").filter({ hasText: student2.name });
        await requestItem.getByRole("button", { name: "Reject" }).click();
        requestItem = facultyPage.locator("#inboxList .request-item").filter({ hasText: student2.name });
        await requestItem.getByText("rejected", { exact: true }).waitFor({ state: "visible" });
        assert.equal(await requestItem.getByRole("button", { name: "Reject" }).count(), 0);

        await studentPage.locator('#navMenu a[data-view="requestsView"]').click();
        await studentPage.locator("#requestsList .status-accepted").waitFor({ state: "visible" });
        await secondPage.locator('#navMenu a[data-view="requestsView"]').click();
        await secondPage.locator("#requestsList .status-rejected").waitFor({ state: "visible" });
        journeyResults.push("faculty profile/link/inbox, accept/reject decisions, and resulting student statuses");

        // Administrator console: account lifecycle, faculty linking, audit and export.
        const student3 = {
            name: `E2E Student Three ${ID}`,
            email: `e2e-student-three-${ID}@example.test`,
            role: "student",
        };
        const student3Page = await context.newPage();
        recordPage(student3Page);
        await register(student3Page, student3);
        await signOut(student3Page);

        const adminPage = await context.newPage();
        recordPage(adminPage);
        await openAuth(adminPage);
        await signInWithPassword(adminPage, ADMIN_EMAIL, ADMIN_PASSWORD);
        assert.match(await adminPage.locator("#userChip").innerText(), /Administrator/);
        await adminPage.locator('#navMenu a[data-view="adminUsersView"]').click();
        await adminPage.waitForFunction(() =>
            /accounts? loaded/i.test(document.querySelector("#adminUsersStatus")?.innerText || ""),
            undefined, { timeout: 30000 });
        await adminPage.locator("#adminUsersList").getByText(student3.email, { exact: false })
            .waitFor({ state: "visible" });

        const accountList = await (await api.get("/admin/users?role=student&limit=200", {
            headers: adminHeaders,
        })).json();
        const student3Account = accountList.find(item => item.email === student3.email);
        assert.ok(student3Account, "registered student should appear in the admin account list");
        const student3Row = adminPage.locator(
            `#adminUsersList [data-admin-user="${student3Account.id}"]`
        );
        assert.equal(await adminPage.locator(`#adminRole-${student3Account.id}`).count(), 1,
            "another account should expose role controls");

        await student3Row.getByRole("button", { name: "Export data" }).click();
        await adminPage.waitForFunction(id => {
            const detail = document.querySelector(`#adminUserDetail-${id}`);
            return detail && /Download JSON/.test(detail.innerText) && /"account"/.test(detail.innerText);
        }, student3Account.id, { timeout: 30000 });

        await student3Row.getByRole("button", { name: "Deactivate" }).click();
        await adminPage.waitForFunction(id =>
            /deactivated/i.test(document.querySelector(`#adminUserStatus-${id}`)?.innerText || ""),
            student3Account.id, { timeout: 30000 });
        const deactivatedLogin = await api.post("/auth/login", {
            data: { email: student3.email, password: PASSWORD },
        });
        assert.equal(deactivatedLogin.status(), 403, "a deactivated account must not sign in");

        await student3Row.getByRole("button", { name: "Activate" }).click();
        await adminPage.waitForFunction(id =>
            /activated/i.test(document.querySelector(`#adminUserStatus-${id}`)?.innerText || ""),
            student3Account.id, { timeout: 30000 });
        const reactivatedLogin = await api.post("/auth/login", {
            data: { email: student3.email, password: PASSWORD },
        });
        assert.equal(reactivatedLogin.status(), 200, "a reactivated account must sign in again");

        await adminPage.locator(`#adminRole-${student3Account.id}`).selectOption("faculty");
        await student3Row.getByRole("button", { name: "Change role" }).click();
        await adminPage.waitForFunction(id =>
            /role changed to faculty/i.test(document.querySelector(`#adminUserStatus-${id}`)?.innerText || ""),
            student3Account.id, { timeout: 30000 });
        const facultyRoleList = await (await api.get("/admin/users?role=faculty&limit=200", {
            headers: adminHeaders,
        })).json();
        assert.ok(facultyRoleList.some(item => item.id === student3Account.id),
            "role change should be persisted by the API");

        await adminPage.locator(`#adminRole-${student3Account.id}`).selectOption("student");
        await student3Row.getByRole("button", { name: "Change role" }).click();
        await adminPage.waitForFunction(id =>
            /role changed to student/i.test(document.querySelector(`#adminUserStatus-${id}`)?.innerText || ""),
            student3Account.id, { timeout: 30000 });

        await adminPage.locator(`#adminPassword-${student3Account.id}`).fill(RESET_PASSWORD);
        await student3Row.getByRole("button", { name: "Reset password" }).click();
        await adminPage.waitForFunction(id =>
            /password updated/i.test(document.querySelector(`#adminUserStatus-${id}`)?.innerText || ""),
            student3Account.id, { timeout: 30000 });
        const resetLogin = await api.post("/auth/login", {
            data: { email: student3.email, password: RESET_PASSWORD },
        });
        assert.equal(resetLogin.status(), 200, "the reset password should authenticate");
        assert.equal(await adminPage.locator(`#adminPassword-${student3Account.id}`).inputValue(), "",
            "the reset password field should be cleared after success");

        // Faculty link management through the console.
        const facultyAccountList = await (await api.get("/admin/users?role=faculty&limit=200", {
            headers: adminHeaders,
        })).json();
        const facultyAccount = facultyAccountList.find(item => item.email === faculty.email);
        assert.ok(facultyAccount, "the faculty account should be listed for administrators");
        const facultyRow = adminPage.locator(
            `#adminUsersList [data-admin-user="${facultyAccount.id}"]`
        );
        await facultyRow.getByRole("button", { name: "Remove link" }).click();
        await adminPage.waitForFunction(id =>
            /link removed/i.test(document.querySelector(`#adminUserStatus-${id}`)?.innerText || ""),
            facultyAccount.id, { timeout: 30000 });
        await facultyPage.locator("#refreshInboxBtn").click();
        await facultyPage.locator("#linkPanel").getByText(/not linked/i)
            .waitFor({ state: "visible", timeout: 30000 });

        await facultyRow.locator(`#adminLinkResearcher-${facultyAccount.id}`)
            .selectOption(String(researcherId));
        await facultyRow.getByRole("button", { name: "Assign link" }).click();
        await adminPage.waitForFunction(id =>
            /linked to/i.test(document.querySelector(`#adminUserStatus-${id}`)?.innerText || ""),
            facultyAccount.id, { timeout: 30000 });
        await facultyPage.locator("#refreshInboxBtn").click();
        await facultyPage.locator("#linkResults").getByText(researcherName, { exact: false })
            .waitFor({ state: "visible", timeout: 30000 });

        // Audit log filtering and rendering.
        await adminPage.locator('#navMenu a[data-view="adminAuditView"]').click();
        await adminPage.waitForFunction(() =>
            /events? loaded/i.test(document.querySelector("#adminAuditStatus")?.innerText || ""),
            undefined, { timeout: 30000 });
        await adminPage.locator("#adminAuditAction").fill("faculty_link.assign");
        const auditResponse = adminPage.waitForResponse(response =>
            response.url().includes("/admin/audit-events") &&
            response.url().includes("action=faculty_link.assign") &&
            response.status() === 200, { timeout: 30000 });
        await adminPage.locator("#refreshAuditBtn").click();
        await auditResponse;
        await adminPage.locator("#adminAuditList .request-item").first()
            .getByText("faculty_link.assign", { exact: false })
            .waitFor({ state: "visible", timeout: 30000 });

        // A student cannot use the administrator API or console.
        await studentPage.evaluate(() => switchView("adminUsersView"));
        await studentPage.waitForFunction(() =>
            /permission/i.test(document.querySelector("#adminUsersStatus")?.innerText || ""),
            undefined, { timeout: 30000 });
        journeyResults.push(
            "admin console account lifecycle, faculty link management, audit and export," +
            " and student denial of the admin API"
        );

        // Expired token is rejected in the real browser and returns the user to sign-in.
        await expireUserSessions(student2.email);
        await secondPage.reload();
        await expectVisible(secondPage.locator("#authShell:not(.hidden)"), 30000);
        assert.match(await secondPage.locator("#authNotice").innerText(), /session has ended|sign in/i);
        await secondPage.waitForFunction(() => !sessionStorage.getItem("researchtwin.sessionToken"));
        journeyResults.push("expired session rejection");

        // Explicit logout clears the student and faculty sessions.
        await signOut(studentPage);
        await signOut(facultyPage);
        journeyResults.push("student and faculty logout revocation");

        assert.ok(!pageErrors.length, `browser page errors: ${pageErrors.join(" | ")}`);
        const expectedConsoleErrors = consoleErrors.filter(message =>
            (expectedNetworkFailure && /ERR_FAILED/i.test(message)) ||
            /status of (401|403|409)\b/i.test(message)
        );
        const unexpectedConsoleErrors = consoleErrors.filter(message => !expectedConsoleErrors.includes(message));
        assert.deepEqual(unexpectedConsoleErrors, [],
            `unexpected browser console errors: ${unexpectedConsoleErrors.join(" | ")}`);
        const unexpectedNetworkFailures = failedRequests.filter(item =>
            !expectedNetworkFailure || !item.url.endsWith("/auth/register"));
        assert.deepEqual(unexpectedNetworkFailures, [], "unexpected browser network requests failed");
        assert.deepEqual(httpErrors.filter(item => ![401, 403, 409].includes(item.status)), [],
            "unexpected browser HTTP errors occurred");

        failed = false;
        console.log(JSON.stringify({
            result: "PASS",
            api: API_URL,
            frontend: FRONTEND_URL,
            database: "isolated temporary SQLite",
            importedResearchers: firstImport.body.imported_count,
            recommendations: recommendations.length,
            rankedScores: recommendations.map(item => item.match_score),
            features: Object.keys(recommendations[0].component_scores),
            journeys: journeyResults,
            browserConsoleErrors: consoleErrors,
            unexpectedBrowserConsoleErrors: unexpectedConsoleErrors,
            browserPageErrors: pageErrors,
            expectedNetworkFailureObserved: expectedNetworkFailure,
            expectedHttpStatuses: httpErrors.filter(item => [401, 403, 409].includes(item.status)).map(item => item.status),
        }, null, 2));
    } catch (error) {
        const screenshot = path.join(ARTIFACT_DIR, "researchtwin-phase3-failure.png");
        const trace = path.join(ARTIFACT_DIR, "researchtwin-phase3-trace.zip");
        const openPage = context.pages().find(page => !page.isClosed());
        if (openPage) await openPage.screenshot({ path: screenshot, fullPage: true }).catch(() => {});
        await context.tracing.stop({ path: trace }).catch(() => {});
        console.error(JSON.stringify({
            result: "FAIL",
            message: error.message,
            stack: error.stack,
            journeysCompleted: journeyResults,
            screenshot,
            trace,
            browserConsoleErrors: consoleErrors,
            browserPageErrors: pageErrors,
            failedRequests,
            httpErrors,
        }, null, 2));
        throw error;
    } finally {
        if (!failed) await context.tracing.stop().catch(() => {});
        await api.dispose();
        await context.close().catch(() => {});
        await browser.close().catch(() => {});
    }
}

main().catch(() => { process.exitCode = 1; });
