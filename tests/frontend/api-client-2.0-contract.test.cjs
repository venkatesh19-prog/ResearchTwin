"use strict";

/*
 * Contract test: every API method referenced by the ResearchTwin 2.0 views
 * must exist on the shared client, use the documented backend endpoint and
 * HTTP method, forward payloads unchanged and keep bearer authentication.
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const { createApi } = require("../../frontend/api-client.js");

const BASE_URL = "https://api.example.test";
const TOKEN = "contract-token";

function memoryStorage(initial = {}) {
  const map = new Map(Object.entries(initial));
  return {
    getItem(key) { return map.has(key) ? map.get(key) : null; },
    setItem(key, value) { map.set(key, String(value)); },
    removeItem(key) { map.delete(key); },
  };
}

function makeApi(responder) {
  const calls = [];
  const api = createApi({
    baseUrl: BASE_URL,
    storage: memoryStorage({ "researchtwin.sessionToken": TOKEN }),
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      if (responder) return responder(url, options);
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    },
  });
  return { api, calls };
}

function parseViewCalls() {
  const source = fs.readFileSync(
    path.join(__dirname, "../../frontend/research-2.0.js"),
    "utf8"
  );
  return [...new Set(
    [...source.matchAll(/client\(\)\.([A-Za-z0-9_]+)/g)].map(match => match[1])
  )].sort();
}

const LITERATURE_PAYLOAD = {
  title: "Attention Is All You Need",
  authors: "Vaswani et al.",
  venue: "NeurIPS",
  year: 2017,
  doi: "10.5555/3295222",
  url: "https://arxiv.org/abs/1706.03762",
  abstract: "Transformer architecture.",
  notes: "Seminal.",
  tags: ["nlp", "transformers"],
  review_status: "reading",
  citation_key: "vaswani2017",
};

const OPPORTUNITY_PAYLOAD = {
  category: "research",
  status: "open",
  title: "Adaptive tutoring study",
  description: "Recruit participants.",
  organization: "Example University",
  location: "Remote",
  url: "",
  deadline_at: 1767225600,
  required_skills: "Python",
  required_research_areas: "education",
  required_expertise: "ML",
  eligibility: "Enrolled students",
};

const TEAM_PAYLOAD = {
  name: "Vision Lab",
  description: "Computer vision",
  research_areas: "vision",
  expertise: "deep learning",
  skills: "PyTorch",
  projects: "Detection",
  publications: "CVPR",
};

// OpportunityUpdate has no `category`: a published call keeps its category,
// so the edit form must never resend it.
const OPPORTUNITY_UPDATE_FIELDS = [
  "status",
  "title",
  "description",
  "organization",
  "location",
  "url",
  "deadline_at",
  "required_skills",
  "required_research_areas",
  "required_expertise",
  "eligibility",
];

function viewSource() {
  return fs.readFileSync(
    path.join(__dirname, "../../frontend/research-2.0.js"),
    "utf8"
  );
}

function balancedObject(source, open) {
  let depth = 0;
  for (let index = open; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    else if (source[index] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(open, index + 1);
    }
  }
  throw new Error("unbalanced object literal in frontend/research-2.0.js");
}

function topLevelKeys(literal) {
  const keys = [];
  let depth = 0;
  for (let index = 1; index < literal.length - 1; index += 1) {
    const char = literal[index];
    if ("[{(".includes(char)) depth += 1;
    else if ("]})".includes(char)) depth -= 1;
    else if (char === "." && depth === 0 && literal[index + 1] === ".") {
      throw new Error("payload builders must list every field explicitly");
    } else if (depth === 0) {
      const key = /^([A-Za-z_$][\w$]*)\s*:/.exec(literal.slice(index));
      if (key) index += key[0].length - 1;
      if (key) keys.push(key[1]);
    }
  }
  return keys;
}

function payloadFields(name) {
  const source = viewSource();
  const definition = source.indexOf(`function ${name}(`);
  assert.notEqual(
    definition,
    -1,
    `frontend/research-2.0.js must define ${name}() so each request sends only the fields its schema accepts`
  );
  const body = source.indexOf("{", source.indexOf(")", definition));
  const open = source.indexOf("{", source.indexOf("return", body));
  assert.notEqual(open, -1, `${name} must return an object literal`);
  return topLevelKeys(balancedObject(source, open));
}

// name, invoke(api), HTTP method, expected path (+query), expected JSON body
const CONTRACTS = [
  ["addLabMember", api => api.addLabMember(3, { user_id: 9 }), "POST", "/labs/3/members", { user_id: 9 }],
  ["addProposalCitation", api => api.addProposalCitation(3, { literature_entry_id: 9 }), "POST", "/proposals/3/citations", { literature_entry_id: 9 }],
  ["addProposalCollaborator", api => api.addProposalCollaborator(3, { user_id: 12, role: "editor" }), "POST", "/proposals/3/collaborators", { user_id: 12, role: "editor" }],
  ["addProposalSection", api => api.addProposalSection(3, { heading: "Background", body: "Text" }), "POST", "/proposals/3/sections", { heading: "Background", body: "Text" }],
  ["addPublicationRevision", api => api.addPublicationRevision(8, { notes: "Addressed comments", submitted_at: 1767225600 }), "POST", "/publication-submissions/8/revisions", { notes: "Addressed comments", submitted_at: 1767225600 }],
  ["addThesisMilestone", api => api.addThesisMilestone(4, { title: "Draft", due_at: 1767225600 }), "POST", "/theses/4/milestones", { title: "Draft", due_at: 1767225600 }],
  ["applyToOpportunity", api => api.applyToOpportunity(5, { message: "I would like to join" }), "POST", "/opportunities/5/applications", { message: "I would like to join" }],
  ["assignInstitutionMember", api => api.assignInstitutionMember(2, 14), "PUT", "/admin/institutions/2/members/14", undefined],
  ["createCollaboration", api => api.createCollaboration({ requester_lab_id: 1, partner_lab_id: 2, title: "Joint lab", description: "" }), "POST", "/interuniversity-collaborations", { requester_lab_id: 1, partner_lab_id: 2, title: "Joint lab", description: "" }],
  ["createInstitution", api => api.createInstitution({ name: "Example University" }), "POST", "/admin/institutions", { name: "Example University" }],
  ["createLab", api => api.createLab({ name: "Vision Lab", description: "Computer vision", research_areas: "vision", visibility: "public" }), "POST", "/labs", { name: "Vision Lab", description: "Computer vision", research_areas: "vision", visibility: "public" }],
  ["createLiteratureEntry", api => api.createLiteratureEntry(LITERATURE_PAYLOAD), "POST", "/literature", LITERATURE_PAYLOAD],
  ["createOpportunity", api => api.createOpportunity(OPPORTUNITY_PAYLOAD), "POST", "/opportunities", OPPORTUNITY_PAYLOAD],
  ["createProposal", api => api.createProposal({ title: "Adaptive tutoring" }), "POST", "/proposals", { title: "Adaptive tutoring" }],
  ["createPublication", api => api.createPublication({ title: "Paper", venue: "NeurIPS", venue_type: "conference", doi: "", url: "", notes: "" }), "POST", "/publication-submissions", { title: "Paper", venue: "NeurIPS", venue_type: "conference", doi: "", url: "", notes: "" }],
  ["createTeam", api => api.createTeam(TEAM_PAYLOAD), "POST", "/teams", TEAM_PAYLOAD],
  ["createThesis", api => api.createThesis({ title: "Thesis", abstract: "Abstract", supervisor_user_id: 7 }), "POST", "/theses", { title: "Thesis", abstract: "Abstract", supervisor_user_id: 7 }],
  ["createWorkspaceComment", api => api.createWorkspaceComment(3, { body: "Looks good", task_id: 11 }), "POST", "/workspaces/3/comments", { body: "Looks good", task_id: 11 }],
  ["createWorkspaceMilestone", api => api.createWorkspaceMilestone(3, { title: "Phase 1", due_at: 1767225600 }), "POST", "/workspaces/3/milestones", { title: "Phase 1", due_at: 1767225600 }],
  ["createWorkspaceTask", api => api.createWorkspaceTask(3, { title: "Draft survey", description: "Section 2", assignee_user_id: 9, due_at: 1767225600 }), "POST", "/workspaces/3/tasks", { title: "Draft survey", description: "Section 2", assignee_user_id: 9, due_at: 1767225600 }],
  ["decideOpportunityApplication", api => api.decideOpportunityApplication(5, 11, { decision: "accept", note: "" }), "PUT", "/opportunities/5/applications/11", { decision: "accept", note: "" }],
  ["decideTeamInvitation", api => api.decideTeamInvitation(4, 8, { decision: "accept" }), "PUT", "/teams/4/invitations/8", { decision: "accept" }],
  ["decideVerification", api => api.decideVerification(7, { decision: "verify", review_note: "Confirmed", expires_in_days: 365 }), "PUT", "/admin/verifications/7", { decision: "verify", review_note: "Confirmed", expires_in_days: 365 }],
  ["deleteLab", api => api.deleteLab(3), "DELETE", "/labs/3", undefined],
  ["deleteLiteratureEntry", api => api.deleteLiteratureEntry(2), "DELETE", "/literature/2", undefined],
  ["deleteOpportunity", api => api.deleteOpportunity(5), "DELETE", "/opportunities/5", undefined],
  ["deleteProposal", api => api.deleteProposal(3), "DELETE", "/proposals/3", undefined],
  ["deleteProposalCitation", api => api.deleteProposalCitation(3, 9), "DELETE", "/proposals/3/citations/9", undefined],
  ["deleteProposalSection", api => api.deleteProposalSection(3, 7), "DELETE", "/proposals/3/sections/7", undefined],
  ["deletePublication", api => api.deletePublication(8), "DELETE", "/publication-submissions/8", undefined],
  ["deleteTeam", api => api.deleteTeam(4), "DELETE", "/teams/4", undefined],
  ["deleteThesis", api => api.deleteThesis(4), "DELETE", "/theses/4", undefined],
  ["deleteThesisMilestone", api => api.deleteThesisMilestone(4, 6), "DELETE", "/theses/4/milestones/6", undefined],
  ["deleteWorkspaceComment", api => api.deleteWorkspaceComment(3, 12), "DELETE", "/workspaces/3/comments/12", undefined],
  ["deleteWorkspaceMilestone", api => api.deleteWorkspaceMilestone(3, 5), "DELETE", "/workspaces/3/milestones/5", undefined],
  ["deleteWorkspaceTask", api => api.deleteWorkspaceTask(3, 11), "DELETE", "/workspaces/3/tasks/11", undefined],
  ["getDepartmentAnalytics", api => api.getDepartmentAnalytics({ department: "Physics", limit: 25 }), "GET", "/analytics/departments?department=Physics&limit=25", undefined],
  ["getKnowledgeGraph", api => api.getKnowledgeGraph({ include_isolated: true }), "GET", "/research-intelligence/knowledge-graph?include_isolated=true", undefined],
  ["getLab", api => api.getLab(3), "GET", "/labs/3", undefined],
  ["getMyInstitution", api => api.getMyInstitution(), "GET", "/institutions/me", undefined],
  ["getMyVerification", api => api.getMyVerification(), "GET", "/faculty/me/researcher-link/verification", undefined],
  ["getOpportunityEligibility", api => api.getOpportunityEligibility(5), "GET", "/opportunities/5/eligibility", undefined],
  ["getProposal", api => api.getProposal(3), "GET", "/proposals/3", undefined],
  ["getProposalVersion", api => api.getProposalVersion(3, 2), "GET", "/proposals/3/versions/2", undefined],
  ["getPublication", api => api.getPublication(8, { include_history: true }), "GET", "/publication-submissions/8?include_history=true", undefined],
  ["getResearchClusters", api => api.getResearchClusters(), "GET", "/research-intelligence/clusters", undefined],
  ["getResearchNetwork", api => api.getResearchNetwork({ min_similarity: 0.2, include_isolated: true }), "GET", "/research-intelligence/network?min_similarity=0.2&include_isolated=true", undefined],
  ["getResearchTrends", api => api.getResearchTrends({ window_days: 30 }), "GET", "/research-intelligence/trends?window_days=30", undefined],
  ["getSearchHistory", api => api.getSearchHistory(), "GET", "/search-history?limit=10", undefined],
  ["getTeam", api => api.getTeam(4), "GET", "/teams/4", undefined],
  ["getTeamRecommendations", api => api.getTeamRecommendations(4, { top_k: 3 }), "POST", "/teams/4/recommendations", { top_k: 3 }],
  ["getThesis", api => api.getThesis(4), "GET", "/theses/4", undefined],
  ["getThesisHistory", api => api.getThesisHistory(4, { limit: 50 }), "GET", "/theses/4/history?limit=50", undefined],
  ["getUniversityAnalytics", api => api.getUniversityAnalytics(), "GET", "/analytics/university", undefined],
  ["getWorkspace", api => api.getWorkspace(3), "GET", "/workspaces/3", undefined],
  ["inviteToTeam", api => api.inviteToTeam(4, { user_id: 12 }), "POST", "/teams/4/invitations", { user_id: 12 }],
  ["listAdminVerifications", api => api.listAdminVerifications({ status: "pending" }), "GET", "/admin/verifications?status=pending", undefined],
  ["listCollaborations", api => api.listCollaborations({ status: "active" }), "GET", "/interuniversity-collaborations?status=active", undefined],
  ["listInstitutionMembers", api => api.listInstitutionMembers(2), "GET", "/admin/institutions/2/members", undefined],
  ["listInstitutions", api => api.listInstitutions(), "GET", "/institutions", undefined, false],
  ["listLabs", api => api.listLabs({ visibility: "public" }), "GET", "/labs?visibility=public", undefined],
  ["listLiterature", api => api.listLiterature({ review_status: "reading", tag: "nlp" }), "GET", "/literature?review_status=reading&tag=nlp", undefined],
  ["listMyApplications", api => api.listMyApplications({ limit: 5 }), "GET", "/students/me/opportunity-applications?limit=5", undefined],
  ["listMyOpportunities", api => api.listMyOpportunities({ limit: 5 }), "GET", "/opportunities/mine?limit=5", undefined],
  ["listMyTeams", api => api.listMyTeams(), "GET", "/teams/me", undefined],
  ["listMyWorkspaces", api => api.listMyWorkspaces(), "GET", "/workspaces/me", undefined],
  ["listOpportunityApplications", api => api.listOpportunityApplications(5, { limit: 5 }), "GET", "/opportunities/5/applications?limit=5", undefined],
  ["listProposalVersions", api => api.listProposalVersions(3, { limit: 5 }), "GET", "/proposals/3/versions?limit=5", undefined],
  ["listProposals", api => api.listProposals({ status: "draft" }), "GET", "/proposals?status=draft", undefined],
  ["listPublications", api => api.listPublications({ status: "submitted" }), "GET", "/publication-submissions?status=submitted", undefined],
  ["listTheses", api => api.listTheses({ status: "active" }), "GET", "/theses?status=active", undefined],
  ["listWorkspaceComments", api => api.listWorkspaceComments(3, { task_id: 7 }), "GET", "/workspaces/3/comments?task_id=7", undefined],
  ["listWorkspaceMilestones", api => api.listWorkspaceMilestones(3), "GET", "/workspaces/3/milestones", undefined],
  ["listWorkspaceTasks", api => api.listWorkspaceTasks(3), "GET", "/workspaces/3/tasks", undefined],
  ["matchOpportunities", api => api.matchOpportunities({ category: "research", top_k: 5, eligible_only: false }), "POST", "/students/me/opportunity-matches", { category: "research", top_k: 5, eligible_only: false }],
  ["predictTopics", api => api.predictTopics({ text: "graph neural networks", top_k: 4 }), "POST", "/research-intelligence/topics/predict", { text: "graph neural networks", top_k: 4 }],
  ["rebuildResearchClusters", api => api.rebuildResearchClusters({ use_semantic: false }), "POST", "/research-intelligence/clusters/rebuild", { use_semantic: false }],
  ["recordSearch", api => api.recordSearch("graph"), "POST", "/search-history", { query: "graph" }],
  ["removeInstitutionMember", api => api.removeInstitutionMember(2, 14), "DELETE", "/admin/institutions/2/members/14", undefined],
  ["removeLabMember", api => api.removeLabMember(3, 9), "DELETE", "/labs/3/members/9", undefined],
  ["removeProposalCollaborator", api => api.removeProposalCollaborator(3, 12), "DELETE", "/proposals/3/collaborators/12", undefined],
  ["removeTeamMember", api => api.removeTeamMember(4, 9), "DELETE", "/teams/4/members/9", undefined],
  ["renameInstitution", api => api.renameInstitution(2, { name: "Renamed University" }), "PUT", "/admin/institutions/2", { name: "Renamed University" }],
  ["searchOpportunities", api => api.searchOpportunities({ category: "research", q: "machine learning" }), "GET", "/opportunities?category=research&q=machine%20learning", undefined],
  ["submitMyVerification", api => api.submitMyVerification({ evidence_reference: "https://example.edu/profile", note: "ORCID" }), "POST", "/faculty/me/researcher-link/verification", { evidence_reference: "https://example.edu/profile", note: "ORCID" }],
  ["updateCollaborationStatus", api => api.updateCollaborationStatus(6, { status: "active", note: "Approved" }), "POST", "/interuniversity-collaborations/6/status", { status: "active", note: "Approved" }],
  ["updateLab", api => api.updateLab(3, { name: "Vision Lab", description: "CV", research_areas: "vision", visibility: "institution" }), "PUT", "/labs/3", { name: "Vision Lab", description: "CV", research_areas: "vision", visibility: "institution" }],
  ["updateLiteratureEntry", api => api.updateLiteratureEntry(2, { review_status: "reviewed" }), "PUT", "/literature/2", { review_status: "reviewed" }],
  ["updateOpportunity", api => api.updateOpportunity(5, { status: "closed" }), "PUT", "/opportunities/5", { status: "closed" }],
  ["updateProposal", api => api.updateProposal(3, { title: "Updated", status: "draft" }), "PUT", "/proposals/3", { title: "Updated", status: "draft" }],
  ["updateProposalSection", api => api.updateProposalSection(3, 7, { heading: "Updated" }), "PUT", "/proposals/3/sections/7", { heading: "Updated" }],
  ["updatePublication", api => api.updatePublication(8, { title: "Updated" }), "PUT", "/publication-submissions/8", { title: "Updated" }],
  ["updatePublicationStatus", api => api.updatePublicationStatus(8, { status: "submitted", note: "Sent" }), "POST", "/publication-submissions/8/status", { status: "submitted", note: "Sent" }],
  ["updateThesis", api => api.updateThesis(4, { title: "Updated" }), "PUT", "/theses/4", { title: "Updated" }],
  ["updateThesisMilestone", api => api.updateThesisMilestone(4, 6, { status: "completed" }), "PUT", "/theses/4/milestones/6", { status: "completed" }],
  ["updateWorkspaceMilestone", api => api.updateWorkspaceMilestone(3, 5, { status: "completed" }), "PUT", "/workspaces/3/milestones/5", { status: "completed" }],
  ["updateWorkspaceTask", api => api.updateWorkspaceTask(3, 11, { status: "done" }), "PUT", "/workspaces/3/tasks/11", { status: "done" }],
  ["withdrawMyApplication", api => api.withdrawMyApplication(5), "DELETE", "/opportunities/5/applications/me", undefined],
];

test("every API method called by the 2.0 views exists on the shared client", async () => {
  const referenced = parseViewCalls();
  assert.ok(referenced.length >= 90, `expected at least 90 referenced methods, got ${referenced.length}`);

  const { api } = makeApi();
  const missing = referenced.filter(name => typeof api[name] !== "function");
  assert.deepEqual(missing, [], `missing client methods: ${missing.join(", ")}`);
});

test("every referenced method appears in the contract table", () => {
  const referenced = parseViewCalls();
  const covered = CONTRACTS.map(entry => entry[0]).sort();
  assert.deepEqual(covered, referenced, "contract table must cover every view-referenced method");
});

test("every contract entry hits the documented endpoint method and payload", async () => {
  for (const [name, invoke, method, expectedPath, expectedBody, auth = true] of CONTRACTS) {
    const { api, calls } = makeApi();
    await invoke(api);

    assert.equal(calls.length, 1, `${name} must issue exactly one request`);
    const [{ url, options }] = calls;

    assert.equal(url, `${BASE_URL}${expectedPath}`, `${name} endpoint mismatch`);
    assert.equal(options.method, method, `${name} HTTP method mismatch`);

    if (auth) {
      assert.equal(options.headers.Authorization, `Bearer ${TOKEN}`, `${name} must send the bearer token`);
    } else {
      assert.equal(options.headers.Authorization, undefined, `${name} must stay unauthenticated`);
    }

    if (expectedBody === undefined) {
      assert.equal(options.body, undefined, `${name} must not send a body`);
      assert.equal(options.headers["Content-Type"], undefined, `${name} must not send JSON content type`);
    } else {
      assert.equal(options.headers["Content-Type"], "application/json", `${name} must send JSON`);
      assert.deepEqual(JSON.parse(options.body), expectedBody, `${name} payload must pass through unchanged`);
    }
  }
});

test("every referenced method rejects with a structured ApiError on server failure", async () => {
  for (const [name, invoke] of CONTRACTS) {
    const { api } = makeApi(() => new Response(
      JSON.stringify({ detail: "server exploded" }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    ));

    await assert.rejects(
      () => invoke(api),
      error => {
        assert.equal(error.name, "ApiError", `${name} must throw ApiError`);
        assert.equal(error.status, 500, `${name} must expose status 500`);
        assert.equal(error.detail, "server exploded", `${name} must surface backend detail`);
        return true;
      }
    );
  }
});

test("editing an opportunity never resends the create-only category", () => {
  assert.deepEqual(payloadFields("opportunityUpdatePayload"), OPPORTUNITY_UPDATE_FIELDS);
});

test("publishing an opportunity sends the edit fields plus category", () => {
  assert.deepEqual(payloadFields("opportunityCreatePayload"), [
    "category",
    ...OPPORTUNITY_UPDATE_FIELDS,
  ]);
});
