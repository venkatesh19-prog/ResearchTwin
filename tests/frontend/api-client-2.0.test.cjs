const test = require("node:test");
const assert = require("node:assert/strict");

const { createApi } = require("../../frontend/api-client.js");

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function memoryStorage(initial = {}) {
  const map = new Map(Object.entries(initial));
  return {
    getItem(key) {
      return map.has(key) ? map.get(key) : null;
    },
    setItem(key, value) {
      map.set(key, String(value));
    },
    removeItem(key) {
      map.delete(key);
    },
  };
}

function makeApi() {
  const calls = [];
  const api = createApi({
    baseUrl: "https://api.example.test",
    storage: memoryStorage({ "researchtwin.sessionToken": "token-123" }),
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return jsonResponse(200, {});
    },
  });
  return { api, calls };
}

function bodyOf(call) {
  return JSON.parse(call.options.body);
}

test("verification submission and decision use documented paths", async () => {
  const { api, calls } = makeApi();

  await api.submitMyVerification({
    evidence_reference: "https://example.edu/profile",
    note: "ORCID",
  });
  await api.decideVerification(7, {
    decision: "verify",
    review_note: "Confirmed",
    expires_in_days: 365,
  });

  assert.equal(
    calls[0].url,
    "https://api.example.test/faculty/me/researcher-link/verification"
  );
  assert.equal(calls[0].options.method, "POST");
  assert.deepEqual(bodyOf(calls[0]), {
    evidence_reference: "https://example.edu/profile",
    note: "ORCID",
  });
  assert.equal(calls[1].url, "https://api.example.test/admin/verifications/7");
  assert.equal(calls[1].options.method, "PUT");
  assert.equal(bodyOf(calls[1]).expires_in_days, 365);
});

test("workspace tasks, comments and milestones use nested paths", async () => {
  const { api, calls } = makeApi();

  await api.createWorkspaceTask(3, {
    title: "Draft survey",
    description: "Section 2",
    assignee_user_id: 9,
    due_at: 1767225600,
  });
  await api.updateWorkspaceTask(3, 11, { status: "done" });
  await api.deleteWorkspaceMilestone(3, 5);
  await api.createWorkspaceComment(3, { body: "Looks good", task_id: 11 });

  assert.equal(calls[0].url, "https://api.example.test/workspaces/3/tasks");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(bodyOf(calls[0]).assignee_user_id, 9);
  assert.equal(calls[1].url, "https://api.example.test/workspaces/3/tasks/11");
  assert.equal(calls[1].options.method, "PUT");
  assert.deepEqual(bodyOf(calls[1]), { status: "done" });
  assert.equal(
    calls[2].url,
    "https://api.example.test/workspaces/3/milestones/5"
  );
  assert.equal(calls[2].options.method, "DELETE");
  assert.equal(calls[3].url, "https://api.example.test/workspaces/3/comments");
  assert.equal(bodyOf(calls[3]).task_id, 11);
});

test("team invitation and recommendation calls carry payloads", async () => {
  const { api, calls } = makeApi();

  await api.inviteToTeam(4, { user_id: 12 });
  await api.decideTeamInvitation(4, 8, { decision: "accept" });
  await api.getTeamRecommendations(4, { top_k: 3 });

  assert.equal(calls[0].url, "https://api.example.test/teams/4/invitations");
  assert.deepEqual(bodyOf(calls[0]), { user_id: 12 });
  assert.equal(
    calls[1].url,
    "https://api.example.test/teams/4/invitations/8"
  );
  assert.equal(calls[1].options.method, "PUT");
  assert.equal(calls[2].url, "https://api.example.test/teams/4/recommendations");
  assert.equal(calls[2].options.method, "POST");
  assert.deepEqual(bodyOf(calls[2]), { top_k: 3 });
});

test("opportunity search, eligibility, applications and withdrawal use real endpoints", async () => {
  const { api, calls } = makeApi();

  await api.searchOpportunities({ category: "research", q: "machine learning" });
  await api.getOpportunityEligibility(5);
  await api.applyToOpportunity(5, { message: "I would like to join" });
  await api.withdrawMyApplication(5);

  assert.equal(
    calls[0].url,
    "https://api.example.test/opportunities?category=research&q=machine%20learning"
  );
  assert.equal(calls[1].url, "https://api.example.test/opportunities/5/eligibility");
  assert.equal(calls[2].options.method, "POST");
  assert.deepEqual(bodyOf(calls[2]), { message: "I would like to join" });
  assert.equal(
    calls[3].url,
    "https://api.example.test/opportunities/5/applications/me"
  );
  assert.equal(calls[3].options.method, "DELETE");
});

test("analytics and research intelligence endpoints use documented queries", async () => {
  const { api, calls } = makeApi();

  await api.getDepartmentAnalytics({ department: "Physics", limit: 25 });
  await api.getResearchNetwork({ min_similarity: 0.2, include_isolated: true });
  await api.predictTopics({ text: "graph neural networks", top_k: 4 });
  await api.rebuildResearchClusters({ min_similarity: 0.18, use_semantic: false });

  assert.equal(
    calls[0].url,
    "https://api.example.test/analytics/departments?department=Physics&limit=25"
  );
  assert.equal(
    calls[1].url,
    "https://api.example.test/research-intelligence/network?min_similarity=0.2&include_isolated=true"
  );
  assert.equal(
    calls[2].url,
    "https://api.example.test/research-intelligence/topics/predict"
  );
  assert.deepEqual(bodyOf(calls[2]), {
    text: "graph neural networks",
    top_k: 4,
  });
  assert.equal(
    calls[3].url,
    "https://api.example.test/research-intelligence/clusters/rebuild"
  );
  assert.equal(bodyOf(calls[3]).use_semantic, false);
});

test("literature filters and CRUD use the literature resource", async () => {
  const { api, calls } = makeApi();

  await api.listLiterature({ review_status: "reading", tag: "nlp" });
  await api.createLiteratureEntry({
    title: "Attention Is All You Need",
    authors: "Vaswani et al.",
    venue: "NeurIPS",
    year: 2017,
    tags: ["nlp"],
    review_status: "reading",
  });
  await api.updateLiteratureEntry(2, { review_status: "reviewed" });

  assert.equal(
    calls[0].url,
    "https://api.example.test/literature?review_status=reading&tag=nlp"
  );
  assert.equal(calls[1].options.method, "POST");
  assert.equal(bodyOf(calls[1]).year, 2017);
  assert.equal(calls[2].url, "https://api.example.test/literature/2");
  assert.equal(calls[2].options.method, "PUT");
});

test("proposal sections, citations and versions use nested paths", async () => {
  const { api, calls } = makeApi();

  await api.createProposal({ title: "Adaptive tutoring" });
  await api.addProposalSection(3, { heading: "Background", body: "..." });
  await api.addProposalCitation(3, { literature_entry_id: 9 });
  await api.getProposalVersion(3, 2);

  assert.equal(calls[0].url, "https://api.example.test/proposals");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(
    calls[1].url,
    "https://api.example.test/proposals/3/sections"
  );
  assert.equal(
    calls[2].url,
    "https://api.example.test/proposals/3/citations"
  );
  assert.equal(
    calls[3].url,
    "https://api.example.test/proposals/3/versions/2"
  );
});

test("thesis and publication lifecycle endpoints use documented bodies", async () => {
  const { api, calls } = makeApi();

  await api.createThesis({ title: "Thesis", abstract: "Abstract" });
  await api.updateThesisMilestone(4, 6, { status: "completed" });
  await api.getThesisHistory(4, { limit: 50 });
  await api.updatePublicationStatus(8, { status: "submitted", note: "Sent" });
  await api.addPublicationRevision(8, {
    notes: "Addressed reviewer comments",
    submitted_at: 1767225600,
  });

  assert.equal(calls[0].url, "https://api.example.test/theses");
  assert.equal(calls[1].url, "https://api.example.test/theses/4/milestones/6");
  assert.deepEqual(bodyOf(calls[1]), { status: "completed" });
  assert.equal(
    calls[2].url,
    "https://api.example.test/theses/4/history?limit=50"
  );
  assert.equal(
    calls[3].url,
    "https://api.example.test/publication-submissions/8/status"
  );
  assert.equal(calls[3].options.method, "POST");
  assert.deepEqual(bodyOf(calls[3]), { status: "submitted", note: "Sent" });
  assert.equal(
    calls[4].url,
    "https://api.example.test/publication-submissions/8/revisions"
  );
});

test("labs, collaborations and institution membership use documented paths", async () => {
  const { api, calls } = makeApi();

  await api.createLab({
    name: "Vision Lab",
    description: "Computer vision",
    research_areas: "vision",
    visibility: "public",
  });
  await api.updateCollaborationStatus(6, {
    status: "active",
    note: "Approved",
  });
  await api.assignInstitutionMember(2, 14);
  await api.removeInstitutionMember(2, 14);

  assert.equal(calls[0].url, "https://api.example.test/labs");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(
    calls[1].url,
    "https://api.example.test/interuniversity-collaborations/6/status"
  );
  assert.equal(calls[1].options.method, "POST");
  assert.equal(
    calls[2].url,
    "https://api.example.test/admin/institutions/2/members/14"
  );
  assert.equal(calls[2].options.method, "PUT");
  assert.equal(calls[3].options.method, "DELETE");
});
