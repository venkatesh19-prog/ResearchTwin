const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '../..');
const html = fs.readFileSync(path.join(root, 'frontend/researchtwin.html'), 'utf8');
const script = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map(m => m[1]).join('\n');
const event = { preventDefault() {} };
const user = role => ({ id: 42, role, full_name: 'Test User', email: 'test@example.org' });
const profile = { research_areas: 'AI', expertise: 'ML', skills: 'Python', courses: 'Math', projects: 'Vision', publications: 'Paper', academic_details: 'MSc', updated_at: 1, profile_completion: 100 };
const faculty = { department: 'CS', designation: 'Professor', research_areas: 'AI', expertise: 'ML', skills: 'Python', publications: 'Paper', projects: 'Vision', profile_url: '', updated_at: 1, profile_completion: 90 };
const roadmap = { researcher: { name: 'Researcher' }, student_skills_provided: true, researcher_skill_count: 2, matched_skills: [], skill_gaps: [], progress: {} };
function deferred() { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; }
const tick = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };

test('recommendation count options stay within the API limit', () => {
    const select = html.match(/<select\b[^>]*\bid="recommendationCount"[^>]*>([\s\S]*?)<\/select>/i);
    assert.ok(select, 'recommendation count control should exist');
    const values = [...select[1].matchAll(/<option\s+value="(\d+)"/gi)].map(match => Number(match[1]));
    assert.ok(values.length > 0, 'recommendation count control should provide options');
    assert.ok(values.every(value => value >= 1 && value <= 10),
        'all selectable counts must pass the backend top_k constraint');
});

// Deliberately small DOM: only tree/attributes/events used by this inline script.
// Layout, native validation and browser rendering are verified separately.
class Element {
    constructor(tag = 'div') { this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {}; this.style = {}; this.attributes = {}; this.value = ''; this.disabled = false; this.checked = false; this.parent = null; this._html = ''; this._text = ''; this.listeners = {}; this.classes = new Set(); this.classList = { add: (...s) => s.forEach(x => this.classes.add(x)), remove: (...s) => s.forEach(x => this.classes.delete(x)), contains: x => this.classes.has(x), toggle: (x, force) => { const on = force === undefined ? !this.classes.has(x) : force; on ? this.classes.add(x) : this.classes.delete(x); return on; } }; }
    set className(v) { this.classes = new Set(v.split(/\s+/).filter(Boolean)); }
    get className() { return [...this.classes].join(' '); }
    setAttribute(k, v) { this.attributes[k] = String(v); if (k === 'id') this.id = v; if (k === 'class') this.className = v; if (k === 'value') this.value = v; if (k === 'disabled') this.disabled = true; if (k.startsWith('data-')) this.dataset[k.slice(5)] = v; }
    getAttribute(k) { return this.attributes[k]; }
    get isConnected() { return Boolean(this.root || this.parent?.isConnected); }
    clear() { this.children.forEach(c => { c.parent = null; }); this.children = []; this._html = ''; this._text = ''; }
    set innerHTML(v) { this.clear(); this._html = String(v); const stack = [this]; for (const token of String(v).matchAll(/<\/?([a-z][\w-]*)\b([^>]*?)>/gi)) { const [full, tag, attrs] = token; if (full.startsWith('</')) { if (stack.length > 1) stack.pop(); continue; } const el = new Element(tag); for (const a of attrs.matchAll(/([\w-]+)(?:="([^"]*)"|'([^']*)')?/g)) el.setAttribute(a[1], a[2] ?? a[3] ?? ''); stack.at(-1).appendChild(el); if (!['input', 'br', 'hr', 'img', 'meta', 'link'].includes(tag)) stack.push(el); } }
    get innerHTML() { return this._html; }
    set textContent(v) { this.clear(); this._text = String(v); }
    get textContent() { return this._text || this._html.replace(/<[^>]*>/g, ' '); }
    appendChild(c) { c.parent = this; this.children.push(c); return c; }
    append(...cs) { cs.forEach(c => this.appendChild(c)); }
    matches(s) { if (s.startsWith('#')) return this.id === s.slice(1); if (s.startsWith('.')) return this.classList.contains(s.slice(1)); const m = s.match(/^(\w+)(?:\[([^=]+)="([^"]+)"\])?$/); return m && this.tagName === m[1].toUpperCase() && (!m[2] || this.getAttribute(m[2]) === m[3] || this[m[2]] === m[3]); }
    querySelectorAll(s) { const choices = s.split(',').map(x => x.trim()); return this.children.flatMap(c => [...(choices.some(q => c.matches(q)) ? [c] : []), ...c.querySelectorAll(s)]); }
    querySelector(s) { return this.querySelectorAll(s)[0] || null; }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    focus() { this.focused = true; }
}
function harness(overrides = {}) {
    const nodes = new Map();
    for (const m of html.matchAll(/<([a-z][\w-]*)\b([^>]*\bid="([^"]+)"[^>]*)>/gi)) { const el = new Element(m[1]); el.root = true; for (const a of m[2].matchAll(/([\w-]+)(?:="([^"]*)")?/g)) el.setAttribute(a[1], a[2] ?? ''); nodes.set(m[3], el); }
    if (nodes.has('recommendationCount')) nodes.get('recommendationCount').value = '5';
    const document = { getElementById: id => nodes.get(id) || [...nodes.values()].flatMap(n => n.querySelectorAll('#' + id))[0] || null, createElement: tag => new Element(tag), querySelectorAll: s => { if (s.startsWith('#') && s.includes(' ')) { const [id, rest] = s.split(' '); return document.getElementById(id.slice(1))?.querySelectorAll(rest) || []; } return [...nodes.values()].filter(n => n.matches(s)); }, querySelector: s => document.querySelectorAll(s)[0] || null };
    const api = { getStudentProfile: async () => ({ ...profile }), getFacultyProfile: async () => ({ ...faculty }), getRecommendations: async () => ({ recommendations: [], profile_completion: 100 }), getResearchers: async () => [], getFacultyResearcherLink: async () => ({ linked: false }), listFacultyCollaborationRequests: async () => ({ requests: [] }), setUnauthorizedHandler() {}, hasSession: () => false, ...overrides };
    const context = vm.createContext({ window: { ResearchTwinAPI: api, addEventListener() {} }, document, URL, console });
    vm.runInContext(script, context);
    const run = code => vm.runInContext(code, context);
    return { api, context, run, $: document.getElementById, state: run('state'), mount(id) { const el = new Element(); el.id = id; document.getElementById('matchesContainer').appendChild(el); return el; }, async start(role = 'student') { await context.enterApp(user(role)); await tick(); } };
}

for (const role of ['student', 'faculty']) {
    const student = role === 'student';
    const load = student ? 'loadStudentProfile' : 'loadFacultyProfile';
    const save = student ? 'handleSaveStudentProfile' : 'handleSaveFacultyProfile';
    const getApi = student ? 'getStudentProfile' : 'getFacultyProfile';
    const putApi = student ? 'saveStudentProfile' : 'saveFacultyProfile';
    const field = student ? 'sSkills' : 'fSkills';
    const button = student ? 'saveStudentBtn' : 'saveFacultyBtn';
    const status = student ? 'studentStatus' : 'facultyStatus';
    const data = student ? profile : faculty;
    test(`${role}: initial load is single-flight, locks editing, and navigation preserves drafts`, async () => {
        const pending = deferred(); let calls = 0;
        const h = harness({ [getApi]: () => { calls++; return pending.promise; } });
        const entry = h.context.enterApp(user(role));
        h.context[load](); h.context[load]();
        assert.equal(calls, 1);
        assert.equal(h.$(field).disabled, true);
        assert.equal(h.$(button).disabled, true);
        pending.resolve(data); await entry; await tick();
        h.$(field).value = 'Unsaved draft';
        await h.context[load]();
        assert.equal(h.$(field).value, 'Unsaved draft');
        assert.equal(h.$(field).disabled, false);
    });
    test(`${role}: failed initial load blocks saving and can retry`, async () => {
        let puts = 0, gets = 0;
        const h = harness({ [getApi]: async () => { if (++gets === 1) throw Error('offline'); return data; }, [putApi]: async () => { puts++; return data; } });
        h.state.user = user(role);
        await h.context[load]();
        await h.context[save](event);
        assert.equal(puts, 0);
        assert.equal(h.$(field).disabled, true);
        await h.context[load]();
        assert.equal(h.$(field).disabled, false);
    });
    for (const outcome of ['success', 'error']) test(`${role}: late save ${outcome} cannot change a new session or release its busy button`, async () => {
        const pending = deferred(); const h = harness({ [putApi]: () => pending.promise });
        await h.start(role);
        const saving = h.context[save](event);
        h.context.resetAppState(); h.state.user = user(role); h.$(field).value = 'User B'; h.$(button).disabled = true; h.$(status).textContent = 'B is saving';
        if (outcome === 'success') pending.resolve({ ...data, skills: 'User A' }); else pending.reject(Error('A failed'));
        await saving;
        assert.equal(h.$(field).value, 'User B');
        assert.equal(h.$(status).textContent, 'B is saving');
        assert.equal(h.$(button).disabled, true);
    });
    test(`${role}: double save submits only once`, async () => {
        const pending = deferred(); let calls = 0; const h = harness({ [putApi]: () => { calls++; return pending.promise; } });
        await h.start(role); const a = h.context[save](event); const b = h.context[save](event);
        assert.equal(calls, 1); pending.resolve(data); await Promise.all([a, b]);
    });
}

test('student save releases busy before a slow model finishes and replaces stale recommendations', async () => {
    const oldModel = deferred(), newModel = deferred(); let calls = 0;
    const h = harness({ getRecommendations: () => (++calls === 1 ? oldModel.promise : newModel.promise), saveStudentProfile: async () => ({ ...profile, skills: 'New saved skills' }) });
    h.context.enterApp(user('student')); await tick();
    let saved = false; h.context.handleSaveStudentProfile(event).then(() => { saved = true; }); await tick();
    assert.equal(h.$('saveStudentBtn').disabled, false);
    assert.equal(saved, true);
    assert.equal(calls, 1, 'new computation waits for previous flight');
    oldModel.resolve({ recommendations: [{ name: 'STALE', match_score: 1 }], profile_completion: 5 }); await tick();
    assert.equal(calls, 2);
    assert.doesNotMatch(h.$('matchesContainer').children.map(x => x.innerHTML).join(''), /STALE/);
    newModel.resolve({ recommendations: [{ name: 'Fresh', match_score: 1 }], profile_completion: 100 }); await tick();
    assert.match(h.$('matchesContainer').children.map(x => x.innerHTML).join(''), /Fresh/);
});

test('recommendations use selected top-K, suppress duplicate clicks, and recover after model errors', async () => {
    const pending = deferred(); const counts = [];
    const h = harness({ getRecommendations: k => { counts.push(k); return pending.promise; } });
    h.state.user = user('student'); h.state.studentProfile = profile;
    // Existing markup must expose this real control.
    assert.ok(h.$('recommendationCount'));
    h.$('recommendationCount').value = '9';
    const a = h.context.refreshRecommendations(); const b = h.context.refreshRecommendations();
    assert.deepEqual(counts, [9]); assert.equal(h.$('refreshMatchesBtn').disabled, true);
    pending.reject(Error('model unavailable')); await Promise.all([a, b]);
    assert.match(h.$('matchStatus').textContent, /model unavailable/); assert.equal(h.$('refreshMatchesBtn').disabled, false);
    h.api.getRecommendations = async k => ({ recommendations: [{ name: 'Retry result ' + k }], profile_completion: 100 });
    await h.context.refreshRecommendations();
    assert.match(h.$('matchesContainer').children[0].innerHTML, /Retry result 9/);
});

test('profile load failure replaces Computing with an actionable recommendation error', async () => {
    const h = harness({ getStudentProfile: async () => { throw Error('offline'); } }); h.state.user = user('student');
    await h.context.refreshRecommendations();
    assert.match(h.$('matchStatus').textContent, /profile.*(retry|again|refresh)/i);
    assert.doesNotMatch(h.$('matchStatus').textContent, /Computing/);
    assert.equal(h.$('refreshMatchesBtn').disabled, false);
});

test('login/register are serialized, including duplicate submit calls', async () => {
    const pending = deferred(); let logins = 0, registrations = 0;
    const h = harness({ login: () => { logins++; return pending.promise; }, register: () => { registrations++; return pending.promise; } });
    h.$('loginEmail').value = 'test@example.org'; h.$('loginPassword').value = 'password';
    h.$('regName').value = 'Test'; h.$('regEmail').value = 'test@example.org'; h.$('regPassword').value = 'password'; h.$('regRole').value = 'student';
    const a = h.context.handleLogin(event); const b = h.context.handleLogin(event); const c = h.context.handleRegister(event);
    assert.equal(logins, 1); assert.equal(registrations, 0); assert.equal(h.$('registerBtn').disabled, true);
    pending.resolve({ user: user('student') }); await Promise.all([a, b, c]); await tick();
    assert.equal(h.$('logoutBtn').disabled, false);
});

test('session restoration is visible and blocks auth submissions', async () => {
    const pending = deferred(); const h = harness({ hasSession: () => true, me: () => pending.promise });
    const restoring = h.context.init();
    assert.equal(h.$('authShell').classList.contains('hidden'), false);
    assert.match(h.$('authNotice').textContent, /restor/i);
    assert.equal(h.$('loginBtn').disabled, true);
    pending.resolve(user('faculty')); await restoring; await tick();
    assert.equal(h.$('authShell').classList.contains('hidden'), true);
});

test('logout invalidates session work immediately and blocks login until revocation settles', async () => {
    const pending = deferred(); let logins = 0; const h = harness({ logout: () => pending.promise, login: async () => { logins++; return { user: user('student') }; } });
    await h.start(); const before = h.state.epoch; const out = h.context.handleLogout();
    assert.ok(h.state.epoch > before); assert.equal(h.state.user, null);
    h.$('loginEmail').value = 'test@example.org'; h.$('loginPassword').value = 'password'; await h.context.handleLogin(event);
    assert.equal(logins, 0); pending.resolve(); await out; assert.equal(h.$('loginBtn').disabled, false);
});

const researchers = [{ id: 1, name: 'Ada', department: 'CS', designation: 'Professor', research_areas: 'AI', expertise: 'Unique expertise', skills: 'Python', publications: 'Unique publication', projects: 'Unique project', experience: 12, profile_url: '' }, { id: 2, name: 'Bea', department: 'Physics', skills: 'R', research_areas: 'Optics' }];
test('directory loads single-flight and combines local department, skill and full-record search', async () => {
    const pending = deferred(); let gets = 0; const h = harness({ getResearchers: () => { gets++; return pending.promise; } });
    const a = h.context.loadDirectory(); const b = h.context.loadDirectory(); assert.equal(gets, 1);
    pending.resolve(researchers); await Promise.all([a, b]);
    assert.ok(h.$('facDepartment')); assert.ok(h.$('facSkill')); assert.match(h.$('facDepartment').innerHTML, /Physics/);
    h.$('facDepartment').value = 'CS'; h.$('facSkill').value = 'python';
    for (const query of ['Unique expertise', 'Unique publication', 'Unique project', '12']) {
        h.$('facSearch').value = query; h.context.renderDirectory(); assert.equal(h.$('facultyList').children.length, 1);
        const result = h.$('facultyList').children[0]; assert.ok(result.querySelector('details')); assert.match(result.innerHTML, /Unique expertise/); assert.match(result.innerHTML, /Unique project/); assert.match(result.innerHTML, /12/);
    }
    h.$('facSkill').value = 'Rust'; h.context.renderDirectory(); assert.equal(h.$('facultyList').children.length, 0); assert.equal(gets, 1);
});

test('faculty save invalidates an in-flight directory response', async () => {
    const pending = deferred(); let gets = 0; const h = harness({ getResearchers: () => ++gets === 1 ? pending.promise : Promise.resolve([{ ...researchers[0], name: 'Updated' }]), saveFacultyProfile: async () => faculty });
    await h.start('faculty'); const loading = h.context.loadDirectory(); await h.context.handleSaveFacultyProfile(event);
    pending.resolve(researchers); await loading; await tick();
    await h.context.loadDirectory();
    assert.equal(h.state.directory[0].name, 'Updated');
});

for (const scenario of ['closed', 'reopened', 'detached']) test(`roadmap ignores delayed GET for a ${scenario} slot`, async () => {
    const pending = deferred(); const second = deferred(); let gets = 0; const h = harness({ getRoadmap: () => ++gets === 1 ? pending.promise : second.promise });
    const slot = h.mount('roadmap-1'); const loading = h.context.toggleRoadmap(1);
    if (scenario === 'detached') { h.$('matchesContainer').innerHTML = ''; h.mount('roadmap-1'); }
    else { await h.context.toggleRoadmap(1); if (scenario === 'reopened') h.context.toggleRoadmap(1); }
    pending.resolve({ ...roadmap, researcher: { name: 'OLD' } }); await loading;
    assert.equal(slot.children.length, 0); assert.doesNotMatch(slot.innerHTML, /OLD/);
    if (scenario === 'reopened') { second.resolve(roadmap); await tick(); }
});

test('milestone update locks all checkboxes, restores failure, and does not reopen after close', async () => {
    const pending = deferred(); const h = harness({ setRoadmapMilestone: () => pending.promise }); const slot = h.mount('roadmap-1'); slot.dataset.open = '1';
    const a = new Element('input'), b = new Element('input'); a.type = b.type = 'checkbox'; a.checked = true; a.dataset = { skill: 'Python', index: '0' }; slot.append(a, b);
    const updating = h.context.updateMilestone(1, slot, a); assert.equal(a.disabled, true); assert.equal(b.disabled, true);
    pending.reject(Error('offline')); await updating; assert.equal(a.checked, false); assert.equal(a.disabled, false); assert.equal(b.disabled, false);
    const late = deferred(); h.api.setRoadmapMilestone = () => late.promise; a.checked = true; const second = h.context.updateMilestone(1, slot, a);
    await h.context.toggleRoadmap(1); late.resolve(roadmap); await second; assert.equal(slot.children.length, 0); assert.notEqual(slot.dataset.open, '1');
});

test('empty researcher skill list does not claim student coverage', () => {
    const h = harness(); const slot = h.mount('roadmap-1'); slot.dataset.open = '1'; h.context.renderRoadmap(slot, { ...roadmap, researcher_skill_count: 0 }, 1);
    const message = slot.children.map(c => c.textContent).join(' '); assert.doesNotMatch(message, /cover their list/); assert.match(message, /no.*skills|not.*(assess|compar)|unavailable/i);
});

test('inbox guides unlinked accounts to admin verification and names the verified linked researcher', async () => {
    const h = harness(); h.state.user = user('faculty'); await h.context.loadFacultyInbox();
    assert.match(h.$('linkPanel').innerHTML, /admin/i); assert.match(h.$('linkPanel').innerHTML, /42/); assert.doesNotMatch(h.$('linkPanel').innerHTML, /This is me|confirm it|switch the linked/);
    assert.match(h.$('linkPanel').innerHTML, /cannot be claimed/i);
    assert.ok(h.$('refreshInboxBtn')); h.api.getFacultyResearcherLink = async () => ({ linked: true, researcher: { id: 1, name: 'Verified Ada' } });
    await h.context.loadFacultyInbox(); assert.match(h.$('linkPanel').innerHTML, /Verified Ada/);
    assert.match(h.$('linkPanel').innerHTML, /Only an administrator can change/i);
});

test('faculty link panel stays read-only even with a loaded directory', async () => {
    const h = harness(); h.state.user = user('faculty');
    h.state.directory = [
        { id: 1, name: 'Dr. Ada Lovelace', department: 'CSE', designation: 'Professor', research_areas: 'AI' },
        { id: 2, name: 'Dr. Grace Hopper', department: 'IT', designation: 'Associate Professor', research_areas: 'Security' }
    ];
    const selfLinkCalls = []; h.api.setFacultyResearcherLink = async (id) => { selfLinkCalls.push(id); return { linked: true }; };
    assert.equal(h.$('linkSearch'), null, 'no directory search may render for self-linking');
    await h.context.loadFacultyInbox();
    assert.equal(h.$('linkResults').querySelectorAll('button').length, 0, 'unlinked inbox must not list claimable records');
    h.api.getFacultyResearcherLink = async () => ({ linked: true, researcher: { id: 1, name: 'Verified Ada', department: 'CSE' } });
    await h.context.loadFacultyInbox();
    const text = h.$('linkResults').children.map(c => c.textContent).join(' ');
    assert.match(text, /Verified Ada/); assert.match(text, /Linked by an administrator/i);
    assert.equal(h.$('linkResults').querySelectorAll('button').length, 0, 'the linked record display must carry no actions');
    assert.deepEqual(selfLinkCalls, [], 'the inbox must never call the self-link API');
});

test('page source exposes no faculty self-link affordance', () => {
    assert.doesNotMatch(html, /This is me/i);
    assert.doesNotMatch(script, /id="linkSearch"|setFacultyResearcherLink\s*\(|You can switch the linked record/);
});

test('inbox shows every student profile field without email and only pending decisions are editable', () => {
    const h = harness();
    for (const status of ['pending', 'accepted', 'rejected']) {
        const item = h.context.renderInboxRecord({ id: 1, status, message: 'Hi', student: { ...profile, full_name: 'Student', email: 'private@example.org' } });
        for (const value of ['AI', 'ML', 'Python', 'Math', 'Vision', 'Paper', 'MSc']) assert.ok(item.innerHTML.includes(value), value);
        assert.doesNotMatch(item.innerHTML, /private@example.org/);
        assert.equal(item.querySelectorAll('button').length, status === 'pending' ? 2 : 0);
    }
});

test('root launcher and legacy app resolve to the canonical authenticated application', () => {
    for (const [file, expected] of [['index.html', 'frontend/researchtwin.html'], ['frontend/index.html', 'researchtwin.html']]) {
        let opened; const source = fs.readFileSync(path.join(root, file), 'utf8'); const code = [...source.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map(m => m[1]).join('\n');
        const context = vm.createContext({ window: { open: url => { opened = url; } } }); vm.runInContext(code, context); context.launchResearchTwin(); assert.equal(opened, expected);
    }
    let redirected; const legacy = fs.readFileSync(path.join(root, 'researchtwin.html'), 'utf8'); const code = [...legacy.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map(m => m[1]).join('\n');
    const location = { search: '?from=legacy', hash: '#profile', replace: url => { redirected = url; } };
    vm.runInNewContext(code, { window: { location }, location }); assert.equal(redirected, 'frontend/researchtwin.html?from=legacy#profile');
});
