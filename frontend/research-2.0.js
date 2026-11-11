/*
 * ResearchTwin 2.0 view module.
 *
 * Loaded as a classic script next to api-client.js. It registers additional
 * authenticated views into the existing sidebar SPA; every view uses only
 * real backend endpoints through the shared api-client instance.
 */
(function (global) {
    "use strict";

    const VIEWS = {};

    const NAV_GROUPS = [
        {
            label: "Research Discovery",
            entries: ["rt20-opportunities", "rt20-applications", "rt20-teams"]
        },
        {
            label: "Collaboration",
            entries: ["rt20-workspaces", "rt20-labs", "rt20-institutions", "rt20-collaborations"]
        },
        {
            label: "Research Outputs",
            entries: ["rt20-literature", "rt20-proposals", "rt20-theses", "rt20-publications"]
        },
        {
            label: "Insights",
            entries: ["rt20-analytics", "rt20-intelligence"]
        },
        {
            label: "Account",
            entries: ["rt20-verification", "rt20-search-history"]
        }
    ];

    const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

    function esc(value) {
        return String(value == null ? "" : value).replace(/[&<>"']/g, ch => ESCAPES[ch]);
    }

    function client() {
        const api = global.ResearchTwinAPI;
        if (!api || typeof api.getSearchHistory !== "function") {
            throw new Error("The API client is not available.");
        }
        return api;
    }

    function currentUser() {
        try {
            if (typeof state !== "undefined" && state && state.user) return state.user;
        } catch (error) {
            // The inline application script has not initialized yet.
        }
        return null;
    }

    function humanError(error) {
        try {
            if (typeof humanizeError === "function") return humanizeError(error);
        } catch (ignored) {
            // Fall through to the local message.
        }
        return String((error && error.message) || "Unexpected error.");
    }

    function statusLabel(value) {
        const text = String(value == null ? "" : value).replace(/_/g, " ");
        return text ? text.charAt(0).toUpperCase() + text.slice(1) : "Unknown";
    }

    function badge(status) {
        const safe = String(status == null ? "" : status).replace(/[^a-z_]/gi, "").toLowerCase();
        return `<span class="rt-badge rt-badge-${esc(safe)}">${esc(statusLabel(status))}</span>`;
    }

    function chips(values) {
        const list = (Array.isArray(values) ? values : []).filter(Boolean);
        if (!list.length) return "";
        return `<div class="rt-chips">${list.map(value =>
            `<span class="rt-chip">${esc(value)}</span>`).join("")}</div>`;
    }

    function fmtDate(epochSeconds) {
        const numeric = Number(epochSeconds);
        if (!Number.isFinite(numeric) || numeric <= 0) return "—";
        return new Date(numeric * 1000).toLocaleDateString(undefined, {
            year: "numeric", month: "short", day: "numeric"
        });
    }

    function isoDate(epochSeconds) {
        const numeric = Number(epochSeconds);
        if (!Number.isFinite(numeric) || numeric <= 0) return "";
        return new Date(numeric * 1000).toISOString().slice(0, 10);
    }

    function epochFromDate(value) {
        const text = String(value || "").trim();
        if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return null;
        const parsed = Date.parse(`${text}T00:00:00Z`);
        return Number.isFinite(parsed) ? Math.floor(parsed / 1000) : null;
    }

    function options(values, current, labels) {
        return values.map(value => {
            const text = labels && labels[value] !== undefined
                ? labels[value]
                : statusLabel(value);
            return `<option value="${esc(value)}"${value === current ? " selected" : ""}>${esc(text)}</option>`;
        }).join("");
    }

    function link(url, label) {
        const text = String(url || "");
        if (!/^https?:\/\//i.test(text)) return esc(label || text);
        return `<a href="${esc(text)}" target="_blank" rel="noopener noreferrer">${esc(label || text)}</a>`;
    }

    function pre(text) {
        if (!text) return "";
        return `<div class="rt-note" style="white-space:pre-wrap;">${esc(text)}</div>`;
    }

    function empty(text) {
        return `<p class="rt-empty">${esc(text)}</p>`;
    }

    function field(source, name) {
        const element = source.querySelector(`[name="${name}"]`);
        return element && element.value != null ? String(element.value).trim() : "";
    }

    function isChecked(source, name) {
        const element = source.querySelector(`[name="${name}"]`);
        return Boolean(element && element.checked);
    }

    function dataId(element) {
        const numeric = Number(element && element.getAttribute("data-id"));
        return Number.isInteger(numeric) && numeric > 0 ? numeric : null;
    }

    function dataNumber(element, name) {
        const numeric = Number(element && element.getAttribute(`data-${name}`));
        return Number.isInteger(numeric) && numeric > 0 ? numeric : null;
    }

    function shell(container, view, toolbarHTML) {
        container.innerHTML = `
            <div class="card">
                <div class="card-title"><i class="fa-solid ${view.icon}"></i> ${esc(view.title)}</div>
                ${view.note ? `<p class="rt-note">${esc(view.note)}</p>` : ""}
                <div class="rt-toolbar">${toolbarHTML || ""}</div>
                <p class="rt-status" role="status"></p>
                <div class="rt-view-body"></div>
                <div class="rt-editor"></div>
            </div>`;
    }

    function statusElement(container) {
        return container.querySelector(".rt-status");
    }

    function setStatus(container, message, tone) {
        const element = statusElement(container);
        if (!element) return;
        element.textContent = message || "";
        element.classList.remove("error", "success");
        if (tone) element.classList.add(tone);
    }

    function setBody(container, html) {
        const body = container.querySelector(".rt-view-body");
        if (body) body.innerHTML = html || "";
    }

    function openEditor(container, html) {
        const editor = container.querySelector(".rt-editor");
        if (editor) editor.innerHTML = html || "";
    }

    function closeEditor(container) {
        openEditor(container, "");
    }

    function viewState(container, initial) {
        if (!container._rtState) container._rtState = Object.assign({}, initial || {});
        return container._rtState;
    }

    function cached(container, key, value) {
        const store = viewState(container);
        if (value !== undefined) store[key] = value;
        return store[key];
    }

    async function loadView(container, view) {
        if (!container || !view) return false;
        const token = (container._rtToken || 0) + 1;
        container._rtToken = token;
        try {
            await view.render(container);
            return token === container._rtToken;
        } catch (error) {
            if (token !== container._rtToken) return false;
            setStatus(container, humanError(error), "error");
            return false;
        }
    }

    function reload(container) {
        const view = VIEWS[container.id];
        return loadView(container, view);
    }

    async function afterWrite(container, message) {
        closeEditor(container);
        const ok = await reload(container);
        if (ok) setStatus(container, message, "success");
    }

    function ensureMounted() {
        const main = document.getElementById("appMain");
        if (!main) return;
        Object.keys(VIEWS).forEach(id => {
            if (document.getElementById(id)) return;
            const section = document.createElement("div");
            section.id = id;
            section.className = "view-section";
            main.appendChild(section);
            wire(section);
        });
    }

    function wire(container) {
        container.addEventListener("click", event => {
            const target = event.target && event.target.closest
                ? event.target.closest("[data-action]")
                : null;
            if (!target || !container.contains(target)) return;
            const view = VIEWS[container.id];
            const action = target.getAttribute("data-action");
            if (!view || !view.actions || !view.actions[action]) return;
            event.preventDefault();
            Promise.resolve(view.actions[action](container, target))
                .catch(error => setStatus(container, humanError(error), "error"));
        });
        container.addEventListener("submit", event => {
            const form = event.target;
            const name = form && form.getAttribute ? form.getAttribute("data-form") : "";
            const view = VIEWS[container.id];
            if (!view || !view.forms || !view.forms[name]) return;
            event.preventDefault();
            const button = form.querySelector('button[type="submit"]');
            if (button) button.disabled = true;
            Promise.resolve(view.forms[name](container, form))
                .catch(error => setStatus(container, humanError(error), "error"))
                .finally(() => { if (button) button.disabled = false; });
        });
    }

    function defineView(config) {
        VIEWS[config.id] = config;
    }

    function navItems(role) {
        const items = [];
        NAV_GROUPS.forEach(group => {
            const entries = group.entries
                .map(id => VIEWS[id])
                .filter(view => view && view.roles.indexOf(role) !== -1);
            if (!entries.length) return;
            items.push([null, null, group.label]);
            entries.forEach(view => items.push([view.id, view.icon, view.title]));
        });
        return items;
    }

    function switchView(viewId) {
        const view = VIEWS[viewId];
        if (!view) return false;
        ensureMounted();
        const container = document.getElementById(viewId);
        if (!container) return false;
        document.querySelectorAll(".view-section")
            .forEach(element => element.classList.remove("active"));
        document.querySelectorAll(".nav-menu a")
            .forEach(element => element.classList.remove("active"));
        container.classList.add("active");
        const navLink = document.querySelector(`.nav-menu a[data-view="${viewId}"]`);
        if (navLink) navLink.classList.add("active");
        const user = currentUser();
        if (!user || view.roles.indexOf(user.role) === -1) {
            container.innerHTML = `
                <div class="card">
                    <div class="card-title"><i class="fa-solid fa-lock"></i> ${esc(view.title)}</div>
                    <p class="rt-note">This area is not available for your account role.</p>
                </div>`;
            return true;
        }
        loadView(container, view);
        return true;
    }

    function reset() {
        Object.keys(VIEWS).forEach(id => {
            const container = document.getElementById(id);
            if (!container) return;
            container._rtToken = (container._rtToken || 0) + 1;
            container._rtState = null;
            container.innerHTML = "";
        });
    }

    /* --------------------------------------------------
     * LITERATURE LIBRARY
     * -------------------------------------------------- */

    const LITERATURE_STATUSES = ["to_read", "reading", "reviewed", "archived"];

    function literatureForm(entry) {
        const e = entry || {};
        return `
        <form class="rt-form" data-form="literature">
            <h4 style="font-size:14px;">${entry ? "Edit literature entry" : "New literature entry"}</h4>
            <input type="hidden" name="entry_id" value="${entry ? entry.id : ""}">
            <div><label>Title</label><input name="title" required maxlength="300" value="${esc(e.title)}"></div>
            <div class="rt-grid-2">
                <div><label>Authors</label><input name="authors" maxlength="2000" value="${esc(e.authors)}"></div>
                <div><label>Venue</label><input name="venue" maxlength="300" value="${esc(e.venue)}"></div>
            </div>
            <div class="rt-grid-2">
                <div><label>Year</label><input name="year" type="number" min="1800" max="2100" value="${e.year || ""}"></div>
                <div><label>Review status</label><select name="review_status">${options(LITERATURE_STATUSES, e.review_status || "to_read")}</select></div>
            </div>
            <div class="rt-grid-2">
                <div><label>DOI</label><input name="doi" maxlength="200" value="${esc(e.doi)}"></div>
                <div><label>URL</label><input name="url" maxlength="500" value="${esc(e.url)}"></div>
            </div>
            <div><label>Tags (comma separated)</label><input name="tags" maxlength="2000" value="${esc((e.tags || []).join(", "))}"></div>
            <div><label>Citation key</label><input name="citation_key" maxlength="100" value="${esc(e.citation_key)}"></div>
            <div><label>Abstract</label><textarea name="abstract" maxlength="10000">${esc(e.abstract)}</textarea></div>
            <div><label>Notes</label><textarea name="notes" maxlength="20000">${esc(e.notes)}</textarea></div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">${entry ? "Save changes" : "Add entry"}</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function literatureItem(entry) {
        return `
        <div class="rt-item">
            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                <h4>${esc(entry.title)} ${badge(entry.review_status)}</h4>
                <span class="rt-meta">${entry.proposal_citation_count
                    ? `${entry.proposal_citation_count} proposal citation(s)`
                    : "Not cited in a proposal"}</span>
            </div>
            <div class="rt-meta">
                ${esc(entry.authors || "Authors not listed")}
                ${entry.year ? ` &middot; ${esc(entry.year)}` : ""}
                ${entry.venue ? ` &middot; ${esc(entry.venue)}` : ""}
            </div>
            ${chips(entry.tags)}
            <div class="rt-actions">
                <button class="btn btn-secondary btn-small" type="button" data-action="open" data-id="${entry.id}">${entry.url ? "Details / edit" : "Edit entry"}</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="delete" data-id="${entry.id}">Delete</button>
                ${entry.url ? `<span class="rt-meta">${link(entry.url, "Open source")}</span>` : ""}
            </div>
        </div>`;
    }

    defineView({
        id: "rt20-literature",
        title: "Literature Library",
        icon: "fa-book-open",
        roles: ["student", "faculty", "admin"],
        note: "Your private reference library. Entries, tags, review status and proposal citation counts come from your account.",
        render(container) {
            const st = viewState(container, { q: "", status: "" });
            shell(container, VIEWS["rt20-literature"], `
                <input type="search" name="litQ" value="${esc(st.q)}" maxlength="200" placeholder="Search title, authors, venue, notes…">
                <select name="litStatus">${options([""].concat(LITERATURE_STATUSES), st.status, { "": "All statuses" })}</select>
                <button type="button" class="btn btn-secondary btn-small" data-action="apply">Apply</button>
                <button type="button" class="btn btn-small" data-action="new"><i class="fa-solid fa-plus"></i> New entry</button>
            `);
            setStatus(container, "Loading your library…");
            return client().listLiterature({
                q: st.q || undefined,
                review_status: st.status || undefined,
                limit: 100
            }).then(payload => {
                const entries = Array.isArray(payload.entries) ? payload.entries : [];
                cached(container, "entries", entries);
                setBody(container, entries.length
                    ? `<div class="rt-list">${entries.map(literatureItem).join("")}</div>`
                    : empty("No literature entries match this filter. Add your first reference."));
                setStatus(container, `Showing ${entries.length} of ${payload.total != null ? payload.total : entries.length} entries.`);
            });
        },
        actions: {
            apply(container) {
                const st = viewState(container);
                st.q = field(container, "litQ");
                st.status = field(container, "litStatus");
                closeEditor(container);
                return reload(container);
            },
            new(container) {
                openEditor(container, literatureForm(null));
            },
            open(container, element) {
                const entry = (cached(container, "entries") || [])
                    .find(item => item.id === dataId(element));
                if (!entry) return;
                openEditor(container, literatureForm(entry));
            },
            cancel(container) {
                closeEditor(container);
            },
            async delete(container, element) {
                const id = dataId(element);
                if (!id) return;
                if (!global.confirm || !global.confirm("Delete this literature entry? Proposal citations to it will be removed.")) return;
                await client().deleteLiteratureEntry(id);
                await afterWrite(container, "Literature entry deleted.");
            }
        },
        forms: {
            async literature(container, form) {
                const id = field(form, "entry_id");
                const year = field(form, "year");
                const payload = {
                    title: field(form, "title"),
                    authors: field(form, "authors"),
                    venue: field(form, "venue"),
                    year: year ? Number(year) : null,
                    doi: field(form, "doi"),
                    url: field(form, "url"),
                    abstract: field(form, "abstract"),
                    notes: field(form, "notes"),
                    tags: field(form, "tags").split(",").map(tag => tag.trim()).filter(Boolean),
                    review_status: field(form, "review_status") || "to_read",
                    citation_key: field(form, "citation_key") || null
                };
                if (id) {
                    await client().updateLiteratureEntry(Number(id), payload);
                    await afterWrite(container, "Literature entry updated.");
                } else {
                    await client().createLiteratureEntry(payload);
                    await afterWrite(container, "Literature entry added.");
                }
            }
        }
    });

    function findById(list, id) {
        return (Array.isArray(list) ? list : []).find(item => item.id === id) || null;
    }

    /* --------------------------------------------------
     * RESEARCH PROPOSALS
     * -------------------------------------------------- */

    const PROPOSAL_STATUSES = ["draft", "submitted", "archived"];

    function proposalCreateForm() {
        return `
        <form class="rt-form" data-form="proposal-create">
            <h4 style="font-size:14px;">New research proposal</h4>
            <div><label>Title</label><input name="title" required maxlength="200"></div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Create draft</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function proposalMetaForm(proposal) {
        return `
        <form class="rt-form" data-form="proposal-meta">
            <h4 style="font-size:14px;">Proposal details</h4>
            <div class="rt-grid-2">
                <div><label>Title</label><input name="title" required maxlength="200" value="${esc(proposal.title)}"></div>
                <div><label>Status</label><select name="status">${options(PROPOSAL_STATUSES, proposal.status)}</select></div>
            </div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Save details</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function proposalSectionForm(section) {
        const s = section || {};
        return `
        <form class="rt-form" data-form="proposal-section">
            <h4 style="font-size:14px;">${section ? "Edit section" : "New section"}</h4>
            <input type="hidden" name="section_id" value="${section ? section.id : ""}">
            <div><label>Heading</label><input name="heading" required maxlength="200" value="${esc(s.heading)}"></div>
            <div><label>Body</label><textarea name="body" maxlength="20000">${esc(s.body)}</textarea></div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">${section ? "Save section" : "Add section"}</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function proposalCitationForm(sections, entries) {
        if (!entries.length) {
            return `${empty("Add entries in Literature Library before citing them.")}
                <div class="rt-actions"><button class="btn btn-secondary btn-small" type="button" data-action="cancel">Close</button></div>`;
        }
        return `
        <form class="rt-form" data-form="proposal-citation">
            <h4 style="font-size:14px;">Cite a library entry</h4>
            <div class="rt-grid-2">
                <div><label>Literature entry</label><select name="literature_entry_id">${entries.map(entry =>
                    `<option value="${entry.id}">${esc(entry.title)}${entry.year ? ` (${esc(entry.year)})` : ""}</option>`).join("")}</select></div>
                <div><label>Attach to section</label><select name="section_id"><option value="">Unassigned</option>${sections.map(section =>
                    `<option value="${section.id}">${esc(section.heading)}</option>`).join("")}</select></div>
            </div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Add citation</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function proposalCollaboratorForm() {
        return `
        <form class="rt-form" data-form="proposal-collaborator">
            <h4 style="font-size:14px;">Add collaborator</h4>
            <div class="rt-grid-2">
                <div><label>User ID</label><input name="user_id" type="number" min="1" required></div>
                <div><label>Role</label><select name="role">${options(["editor", "viewer"], "viewer")}</select></div>
            </div>
            <p class="rt-meta">The collaborator uses their own ResearchTwin account ID.</p>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Add collaborator</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function proposalItem(proposal) {
        return `
        <div class="rt-item">
            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                <h4>${esc(proposal.title)} ${badge(proposal.status)}</h4>
                <span class="rt-meta">${esc(statusLabel(proposal.access_role))} access</span>
            </div>
            <div class="rt-meta">
                ${proposal.section_count} section(s) &middot; ${proposal.citation_count} citation(s)
                &middot; version ${proposal.latest_version} &middot; updated ${fmtDate(proposal.updated_at)}
            </div>
            <div class="rt-actions">
                <button class="btn btn-secondary btn-small" type="button" data-action="open" data-id="${proposal.id}">Open</button>
                ${proposal.access_role === "owner"
                    ? `<button class="btn btn-secondary btn-small" type="button" data-action="delete" data-id="${proposal.id}">Delete</button>`
                    : ""}
            </div>
        </div>`;
    }

    function proposalDetailHTML(proposal, versions) {
        const isWriter = proposal.access_role !== "viewer";
        const isOwner = proposal.access_role === "owner";

        const sectionHTML = proposal.sections.length
            ? proposal.sections.map(section => `
                <div class="rt-item">
                    <h4>${esc(section.heading)}</h4>
                    ${pre(section.body)}
                    ${isWriter ? `<div class="rt-actions">
                        <button class="btn btn-secondary btn-small" type="button" data-action="section-edit" data-id="${section.id}">Edit section</button>
                        <button class="btn btn-secondary btn-small" type="button" data-action="section-delete" data-id="${section.id}">Delete section</button>
                    </div>` : ""}
                </div>`).join("")
            : empty("No sections yet.");

        const citationHTML = proposal.citations.length
            ? `<div class="rt-list">${proposal.citations.map(citation => `
                <div class="rt-item">
                    <h4>${esc(citation.title)}${citation.year ? ` <span class="rt-meta">(${esc(citation.year)})</span>` : ""}</h4>
                    <div class="rt-meta">
                        ${esc(citation.authors || "Authors not listed")}
                        ${citation.venue ? ` &middot; ${esc(citation.venue)}` : ""}
                        ${citation.citation_key ? ` &middot; [${esc(citation.citation_key)}]` : ""}
                        ${citation.url ? ` &middot; ${link(citation.url, "source")}` : ""}
                    </div>
                    ${isWriter ? `<div class="rt-actions">
                        <button class="btn btn-secondary btn-small" type="button" data-action="citation-delete" data-id="${citation.id}">Remove citation</button>
                    </div>` : ""}
                </div>`).join("")}</div>`
            : empty("No citations yet.");

        const collaboratorHTML = proposal.collaborators.length
            ? `<div class="rt-list">${proposal.collaborators.map(collaborator => `
                <div class="rt-item">
                    <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                        <h4>${esc(collaborator.full_name || `User ${collaborator.user_id}`)}</h4>
                        ${badge(collaborator.role)}
                    </div>
                    ${isOwner ? `<div class="rt-actions">
                        <button class="btn btn-secondary btn-small" type="button" data-action="collaborator-remove" data-user="${collaborator.user_id}">Remove</button>
                    </div>` : ""}
                </div>`).join("")}</div>`
            : empty("No collaborators yet.");

        const versionHTML = versions.length
            ? `<div class="rt-list">${versions.map(version => `
                <div class="rt-item">
                    <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                        <h4>Version ${version.version}</h4>
                        ${badge(version.status)}
                    </div>
                    <div class="rt-meta">
                        ${version.section_count} section(s) &middot; ${version.citation_count} citation(s)
                        &middot; saved ${fmtDate(version.created_at)}
                    </div>
                    <div class="rt-actions">
                        <button class="btn btn-secondary btn-small" type="button" data-action="version-view" data-id="${version.version}">View snapshot</button>
                    </div>
                </div>`).join("")}</div>`
            : empty("No versions recorded yet.");

        return `
        <div class="rt-detail">
            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                <h3>${esc(proposal.title)} ${badge(proposal.status)}</h3>
                <span class="rt-meta">${esc(statusLabel(proposal.access_role))} access</span>
            </div>
            <p class="rt-meta">
                Owner: ${esc(proposal.owner.full_name || `User ${proposal.owner.user_id}`)}
                &middot; latest version ${proposal.latest_version}
                &middot; updated ${fmtDate(proposal.updated_at)}
            </p>
            ${isOwner ? `<div class="rt-actions">
                <button class="btn btn-secondary btn-small" type="button" data-action="meta-edit">Edit details</button>
            </div>` : ""}
        </div>

        <h4 style="margin-top:18px;font-size:14px;">Sections</h4>
        ${sectionHTML}
        ${isWriter ? `<button class="btn btn-small" type="button" data-action="section-new"><i class="fa-solid fa-plus"></i> Add section</button>` : ""}

        <h4 style="margin-top:18px;font-size:14px;">Citations</h4>
        ${citationHTML}
        ${isWriter ? `<button class="btn btn-secondary btn-small" type="button" data-action="citation-new">Cite library entry</button>` : ""}

        <h4 style="margin-top:18px;font-size:14px;">Collaborators</h4>
        ${collaboratorHTML}
        ${isOwner ? `<button class="btn btn-secondary btn-small" type="button" data-action="collaborator-new">Add collaborator</button>` : ""}

        <h4 style="margin-top:18px;font-size:14px;">Versions</h4>
        ${versionHTML}`;
    }

    async function renderProposalDetail(container) {
        const st = viewState(container);
        const proposalId = st.detailId;
        shell(container, VIEWS["rt20-proposals"], `
            <button class="btn btn-secondary btn-small" type="button" data-action="back">
                <i class="fa-solid fa-arrow-left"></i> Back to proposals
            </button>`);
        setStatus(container, "Loading proposal…");
        const [proposal, versionPayload, literature] = await Promise.all([
            client().getProposal(proposalId),
            client().listProposalVersions(proposalId, { limit: 50 }),
            client().listLiterature({ limit: 100 })
        ]);
        cached(container, "detail", proposal);
        cached(container, "versions", versionPayload.versions || []);
        cached(container, "literature", literature.entries || []);
        setBody(container, proposalDetailHTML(proposal, versionPayload.versions || []));
        setStatus(container, `Latest version ${proposal.latest_version}.`);
    }

    defineView({
        id: "rt20-proposals",
        title: "Research Proposals",
        icon: "fa-file-signature",
        roles: ["student", "faculty", "admin"],
        note: "Draft proposals with sections, literature citations, collaborators and saved versions.",
        render(container) {
            const st = viewState(container, { detailId: null });
            if (st.detailId) return renderProposalDetail(container);
            shell(container, VIEWS["rt20-proposals"], `
                <button class="btn btn-small" type="button" data-action="new"><i class="fa-solid fa-plus"></i> New proposal</button>
            `);
            setStatus(container, "Loading proposals…");
            return client().listProposals({ limit: 100 }).then(payload => {
                const proposals = Array.isArray(payload.proposals) ? payload.proposals : [];
                cached(container, "proposals", proposals);
                setBody(container, proposals.length
                    ? `<div class="rt-list">${proposals.map(proposalItem).join("")}</div>`
                    : empty("No proposals yet. Create your first draft."));
                setStatus(container, `Showing ${proposals.length} of ${payload.total != null ? payload.total : proposals.length} proposals.`);
            });
        },
        actions: {
            new(container) {
                openEditor(container, proposalCreateForm());
            },
            open(container, element) {
                viewState(container).detailId = dataId(element);
                closeEditor(container);
                return reload(container);
            },
            back(container) {
                viewState(container).detailId = null;
                closeEditor(container);
                return reload(container);
            },
            async delete(container, element) {
                const id = dataId(element);
                if (!id) return;
                if (!global.confirm || !global.confirm("Delete this proposal, its sections, citations and versions?")) return;
                await client().deleteProposal(id);
                await afterWrite(container, "Proposal deleted.");
            },
            "meta-edit"(container) {
                const detail = cached(container, "detail");
                if (detail) openEditor(container, proposalMetaForm(detail));
            },
            "section-new"(container) {
                openEditor(container, proposalSectionForm(null));
            },
            "section-edit"(container, element) {
                const detail = cached(container, "detail") || { sections: [] };
                const section = findById(detail.sections, dataId(element));
                if (section) openEditor(container, proposalSectionForm(section));
            },
            async "section-delete"(container, element) {
                const detail = cached(container, "detail");
                const sectionId = dataId(element);
                if (!detail || !sectionId) return;
                if (!global.confirm || !global.confirm("Delete this section? Citations attached to it stay in the proposal.")) return;
                await client().deleteProposalSection(detail.id, sectionId);
                await afterWrite(container, "Section deleted.");
            },
            "citation-new"(container) {
                const detail = cached(container, "detail");
                if (!detail) return;
                openEditor(container, proposalCitationForm(detail.sections, cached(container, "literature") || []));
            },
            async "citation-delete"(container, element) {
                const detail = cached(container, "detail");
                const citationId = dataId(element);
                if (!detail || !citationId) return;
                if (!global.confirm || !global.confirm("Remove this citation from the proposal?")) return;
                await client().deleteProposalCitation(detail.id, citationId);
                await afterWrite(container, "Citation removed.");
            },
            "collaborator-new"(container) {
                openEditor(container, proposalCollaboratorForm());
            },
            async "collaborator-remove"(container, element) {
                const detail = cached(container, "detail");
                const userId = dataNumber(element, "user");
                if (!detail || !userId) return;
                if (!global.confirm || !global.confirm("Remove this collaborator from the proposal?")) return;
                await client().removeProposalCollaborator(detail.id, userId);
                await afterWrite(container, "Collaborator removed.");
            },
            async "version-view"(container, element) {
                const detail = cached(container, "detail");
                const version = dataId(element);
                if (!detail || !version) return;
                const snapshot = await client().getProposalVersion(detail.id, version);
                const data = snapshot.snapshot || {};
                openEditor(container, `
                    <div class="rt-detail">
                        <h4>Version ${version} snapshot</h4>
                        <p class="rt-meta">
                            ${esc(data.title || "")} &middot; ${esc(statusLabel(data.status))}
                            &middot; saved ${fmtDate(snapshot.created_at)}
                        </p>
                        ${(data.sections || []).map(section => `
                            <div class="rt-item">
                                <h4>${esc(section.heading)}</h4>
                                ${pre(section.body)}
                            </div>`).join("") || empty("No sections in this version.")}
                        <div class="rt-actions">
                            <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Close</button>
                        </div>
                    </div>`);
            },
            cancel(container) {
                closeEditor(container);
            }
        },
        forms: {
            async "proposal-create"(container, form) {
                const created = await client().createProposal({ title: field(form, "title") });
                viewState(container).detailId = created.id;
                await afterWrite(container, "Proposal created.");
            },
            async "proposal-meta"(container, form) {
                const detail = cached(container, "detail");
                if (!detail) return;
                await client().updateProposal(detail.id, {
                    title: field(form, "title"),
                    status: field(form, "status")
                });
                await afterWrite(container, "Proposal details saved.");
            },
            async "proposal-section"(container, form) {
                const detail = cached(container, "detail");
                if (!detail) return;
                const sectionId = field(form, "section_id");
                const payload = { heading: field(form, "heading"), body: field(form, "body") };
                if (sectionId) {
                    await client().updateProposalSection(detail.id, Number(sectionId), payload);
                    await afterWrite(container, "Section saved.");
                } else {
                    await client().addProposalSection(detail.id, payload);
                    await afterWrite(container, "Section added.");
                }
            },
            async "proposal-citation"(container, form) {
                const detail = cached(container, "detail");
                if (!detail) return;
                const sectionId = field(form, "section_id");
                await client().addProposalCitation(detail.id, {
                    literature_entry_id: Number(field(form, "literature_entry_id")),
                    section_id: sectionId ? Number(sectionId) : null
                });
                await afterWrite(container, "Citation added.");
            },
            async "proposal-collaborator"(container, form) {
                const detail = cached(container, "detail");
                if (!detail) return;
                await client().addProposalCollaborator(detail.id, {
                    user_id: Number(field(form, "user_id")),
                    role: field(form, "role") || "viewer"
                });
                await afterWrite(container, "Collaborator added.");
            }
        }
    });

    /* --------------------------------------------------
     * THESES
     * -------------------------------------------------- */

    const THESIS_STATUSES = ["proposed", "in_progress", "submitted", "defended", "completed", "withdrawn"];
    const THESIS_TRANSITIONS = {
        proposed: ["in_progress", "withdrawn"],
        in_progress: ["submitted", "withdrawn"],
        submitted: ["defended", "in_progress", "withdrawn"],
        defended: ["completed", "in_progress"],
        completed: [],
        withdrawn: []
    };

    function thesisCreateForm() {
        return `
        <form class="rt-form" data-form="thesis-create">
            <h4 style="font-size:14px;">New thesis</h4>
            <div><label>Title</label><input name="title" required maxlength="300"></div>
            <div><label>Abstract</label><textarea name="abstract" maxlength="20000"></textarea></div>
            <div><label>Supervisor user ID (optional)</label><input name="supervisor_user_id" type="number" min="1"></div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Create thesis</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function thesisMetaForm(thesis) {
        return `
        <form class="rt-form" data-form="thesis-meta">
            <h4 style="font-size:14px;">Thesis details</h4>
            <div><label>Title</label><input name="title" required maxlength="300" value="${esc(thesis.title)}"></div>
            <div><label>Abstract</label><textarea name="abstract" maxlength="20000">${esc(thesis.abstract)}</textarea></div>
            <div><label>Supervisor user ID (blank clears)</label><input name="supervisor_user_id" type="number" min="1" value="${thesis.supervisor ? thesis.supervisor.user_id : ""}"></div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Save details</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function thesisStatusForm(thesis) {
        const allowed = THESIS_TRANSITIONS[thesis.status] || [];
        if (!allowed.length) {
            return `${empty("This thesis status is final.")}
                <div class="rt-actions"><button class="btn btn-secondary btn-small" type="button" data-action="cancel">Close</button></div>`;
        }
        return `
        <form class="rt-form" data-form="thesis-status">
            <h4 style="font-size:14px;">Change thesis status</h4>
            <div class="rt-grid-2">
                <div><label>New status</label><select name="status">${options(allowed, allowed[0])}</select></div>
                <div><label>Progress note</label><input name="note" maxlength="2000"></div>
            </div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Update status</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function thesisMilestoneForm(milestone) {
        const m = milestone || {};
        return `
        <form class="rt-form" data-form="thesis-milestone">
            <h4 style="font-size:14px;">${milestone ? "Edit milestone" : "New milestone"}</h4>
            <input type="hidden" name="milestone_id" value="${milestone ? milestone.id : ""}">
            <div class="rt-grid-2">
                <div><label>Title</label><input name="title" required maxlength="200" value="${esc(m.title)}"></div>
                <div><label>Due date</label><input name="due_at" type="date" value="${isoDate(m.due_at)}"></div>
            </div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">${milestone ? "Save milestone" : "Add milestone"}</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function thesisItem(thesis) {
        return `
        <div class="rt-item">
            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                <h4>${esc(thesis.title)} ${badge(thesis.status)}</h4>
                <span class="rt-meta">${esc(statusLabel(thesis.access_role))} access</span>
            </div>
            <div class="rt-meta">
                ${thesis.open_milestone_count} open of ${thesis.milestone_count} milestone(s)
                &middot; next deadline ${fmtDate(thesis.next_deadline)}
                &middot; updated ${fmtDate(thesis.updated_at)}
            </div>
            <div class="rt-actions">
                <button class="btn btn-secondary btn-small" type="button" data-action="open" data-id="${thesis.id}">Open</button>
                ${thesis.access_role === "owner"
                    ? `<button class="btn btn-secondary btn-small" type="button" data-action="delete" data-id="${thesis.id}">Delete</button>`
                    : ""}
            </div>
        </div>`;
    }

    function thesisDetailHTML(thesis, history) {
        const isOwner = thesis.access_role === "owner";
        const milestoneHTML = thesis.milestones.length
            ? `<div class="rt-list">${thesis.milestones.map(milestone => `
                <div class="rt-item">
                    <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                        <h4>${esc(milestone.title)} ${badge(milestone.status)}</h4>
                        <span class="rt-meta">due ${fmtDate(milestone.due_at)}</span>
                    </div>
                    <div class="rt-actions">
                        <button class="btn btn-secondary btn-small" type="button" data-action="milestone-toggle"
                                data-id="${milestone.id}" data-status="${milestone.status === "completed" ? "pending" : "completed"}">
                            ${milestone.status === "completed" ? "Reopen" : "Mark complete"}
                        </button>
                        <button class="btn btn-secondary btn-small" type="button" data-action="milestone-edit" data-id="${milestone.id}">Edit</button>
                        ${isOwner ? `<button class="btn btn-secondary btn-small" type="button" data-action="milestone-delete" data-id="${milestone.id}">Delete</button>` : ""}
                    </div>
                </div>`).join("")}</div>`
            : empty("No milestones yet.");

        const historyHTML = history.length
            ? `<div class="rt-list">${history.map(event => `
                <div class="rt-item">
                    <div class="rt-meta">${fmtDate(event.created_at)} &middot; ${esc(event.actor_name || "System")}</div>
                    <div>${esc(statusLabel(event.event_type))}${event.note ? ` — ${esc(event.note)}` : ""}</div>
                    ${event.from_status || event.to_status
                        ? `<div class="rt-meta">${esc(statusLabel(event.from_status || "—"))} → ${esc(statusLabel(event.to_status || "—"))}</div>`
                        : ""}
                </div>`).join("")}</div>`
            : empty("No progress events yet.");

        return `
        <div class="rt-detail">
            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                <h3>${esc(thesis.title)} ${badge(thesis.status)}</h3>
                <span class="rt-meta">${esc(statusLabel(thesis.access_role))} access</span>
            </div>
            <p class="rt-meta">
                Owner: ${esc(thesis.owner.full_name || `User ${thesis.owner.user_id}`)}
                &middot; supervisor: ${thesis.supervisor
                    ? esc(thesis.supervisor.full_name || `User ${thesis.supervisor.user_id}`)
                    : "not assigned"}
                &middot; updated ${fmtDate(thesis.updated_at)}
            </p>
            ${pre(thesis.abstract)}
            <div class="rt-actions">
                ${isOwner ? `<button class="btn btn-secondary btn-small" type="button" data-action="meta-edit">Edit details</button>` : ""}
                ${isOwner ? `<button class="btn btn-secondary btn-small" type="button" data-action="status-edit">Change status</button>` : ""}
            </div>
        </div>

        <h4 style="margin-top:18px;font-size:14px;">Milestones</h4>
        ${milestoneHTML}
        <button class="btn btn-secondary btn-small" type="button" data-action="milestone-new">Add milestone</button>

        <h4 style="margin-top:18px;font-size:14px;">Progress history</h4>
        ${historyHTML}`;
    }

    async function renderThesisDetail(container) {
        const st = viewState(container);
        const thesisId = st.detailId;
        shell(container, VIEWS["rt20-theses"], `
            <button class="btn btn-secondary btn-small" type="button" data-action="back">
                <i class="fa-solid fa-arrow-left"></i> Back to theses
            </button>`);
        setStatus(container, "Loading thesis…");
        const [thesis, historyPayload] = await Promise.all([
            client().getThesis(thesisId),
            client().getThesisHistory(thesisId, { limit: 100 })
        ]);
        cached(container, "detail", thesis);
        setBody(container, thesisDetailHTML(thesis, historyPayload.events || []));
        setStatus(container, `${thesis.milestones.length} milestone(s) tracked.`);
    }

    defineView({
        id: "rt20-theses",
        title: "Thesis Tracking",
        icon: "fa-graduation-cap",
        roles: ["student", "faculty", "admin"],
        note: "Thesis progress with supervisor oversight, milestones and a full progress history.",
        render(container) {
            const st = viewState(container, { detailId: null });
            if (st.detailId) return renderThesisDetail(container);
            const user = currentUser();
            const canCreate = user && user.role === "student";
            shell(container, VIEWS["rt20-theses"], canCreate
                ? `<button class="btn btn-small" type="button" data-action="new"><i class="fa-solid fa-plus"></i> New thesis</button>`
                : "");
            setStatus(container, "Loading theses…");
            return client().listTheses({ limit: 100 }).then(payload => {
                const theses = Array.isArray(payload.theses) ? payload.theses : [];
                setBody(container, theses.length
                    ? `<div class="rt-list">${theses.map(thesisItem).join("")}</div>`
                    : empty("No theses yet. Students can create their first thesis here."));
                setStatus(container, `Showing ${theses.length} of ${payload.total != null ? payload.total : theses.length} theses.`);
            });
        },
        actions: {
            new(container) {
                openEditor(container, thesisCreateForm());
            },
            open(container, element) {
                viewState(container).detailId = dataId(element);
                closeEditor(container);
                return reload(container);
            },
            back(container) {
                viewState(container).detailId = null;
                closeEditor(container);
                return reload(container);
            },
            async delete(container, element) {
                const id = dataId(element);
                if (!id) return;
                if (!global.confirm || !global.confirm("Delete this thesis, its milestones and history?")) return;
                await client().deleteThesis(id);
                await afterWrite(container, "Thesis deleted.");
            },
            "meta-edit"(container) {
                const detail = cached(container, "detail");
                if (detail) openEditor(container, thesisMetaForm(detail));
            },
            "status-edit"(container) {
                const detail = cached(container, "detail");
                if (detail) openEditor(container, thesisStatusForm(detail));
            },
            "milestone-new"(container) {
                openEditor(container, thesisMilestoneForm(null));
            },
            "milestone-edit"(container, element) {
                const detail = cached(container, "detail") || { milestones: [] };
                const milestone = findById(detail.milestones, dataId(element));
                if (milestone) openEditor(container, thesisMilestoneForm(milestone));
            },
            async "milestone-toggle"(container, element) {
                const detail = cached(container, "detail");
                const milestoneId = dataId(element);
                const status = element.getAttribute("data-status");
                if (!detail || !milestoneId || !status) return;
                await client().updateThesisMilestone(detail.id, milestoneId, { status });
                await afterWrite(container, status === "completed" ? "Milestone completed." : "Milestone reopened.");
            },
            async "milestone-delete"(container, element) {
                const detail = cached(container, "detail");
                const milestoneId = dataId(element);
                if (!detail || !milestoneId) return;
                if (!global.confirm || !global.confirm("Delete this milestone?")) return;
                await client().deleteThesisMilestone(detail.id, milestoneId);
                await afterWrite(container, "Milestone deleted.");
            },
            cancel(container) {
                closeEditor(container);
            }
        },
        forms: {
            async "thesis-create"(container, form) {
                const supervisor = field(form, "supervisor_user_id");
                const created = await client().createThesis({
                    title: field(form, "title"),
                    abstract: field(form, "abstract"),
                    supervisor_user_id: supervisor ? Number(supervisor) : null
                });
                viewState(container).detailId = created.id;
                await afterWrite(container, "Thesis created.");
            },
            async "thesis-meta"(container, form) {
                const detail = cached(container, "detail");
                if (!detail) return;
                const supervisor = field(form, "supervisor_user_id");
                await client().updateThesis(detail.id, {
                    title: field(form, "title"),
                    abstract: field(form, "abstract"),
                    supervisor_user_id: supervisor ? Number(supervisor) : null
                });
                await afterWrite(container, "Thesis details saved.");
            },
            async "thesis-status"(container, form) {
                const detail = cached(container, "detail");
                if (!detail) return;
                await client().updateThesis(detail.id, {
                    status: field(form, "status"),
                    note: field(form, "note")
                });
                await afterWrite(container, "Thesis status updated.");
            },
            async "thesis-milestone"(container, form) {
                const detail = cached(container, "detail");
                if (!detail) return;
                const milestoneId = field(form, "milestone_id");
                const payload = {
                    title: field(form, "title"),
                    due_at: epochFromDate(field(form, "due_at"))
                };
                if (milestoneId) {
                    await client().updateThesisMilestone(detail.id, Number(milestoneId), payload);
                    await afterWrite(container, "Milestone saved.");
                } else {
                    await client().addThesisMilestone(detail.id, payload);
                    await afterWrite(container, "Milestone added.");
                }
            }
        }
    });

    /* --------------------------------------------------
     * PUBLICATIONS
     * -------------------------------------------------- */

    const PUBLICATION_STATUSES = [
        "draft", "submitted", "under_review", "revision_requested",
        "accepted", "rejected", "published", "withdrawn"
    ];
    const PUBLICATION_TRANSITIONS = {
        draft: ["submitted", "withdrawn"],
        submitted: ["under_review", "rejected", "withdrawn"],
        under_review: ["revision_requested", "accepted", "rejected", "withdrawn"],
        revision_requested: ["submitted", "withdrawn"],
        accepted: ["published", "withdrawn"],
        rejected: [],
        published: [],
        withdrawn: []
    };
    const PUBLICATION_REVISION_STATUSES = ["submitted", "under_review", "revision_requested", "accepted"];
    const VENUE_TYPES = ["journal", "conference", "workshop", "book_chapter", "other"];
    const VENUE_LABELS = {
        journal: "Journal", conference: "Conference", workshop: "Workshop",
        book_chapter: "Book chapter", other: "Other"
    };

    function publicationForm(submission) {
        const s = submission || {};
        return `
        <form class="rt-form" data-form="publication">
            <h4 style="font-size:14px;">${submission ? "Edit submission" : "New submission"}</h4>
            <input type="hidden" name="submission_id" value="${submission ? submission.id : ""}">
            <div><label>Title</label><input name="title" required maxlength="300" value="${esc(s.title)}"></div>
            <div class="rt-grid-2">
                <div><label>Venue</label><input name="venue" maxlength="300" value="${esc(s.venue)}"></div>
                <div><label>Venue type</label><select name="venue_type">${options(VENUE_TYPES, s.venue_type || "journal", VENUE_LABELS)}</select></div>
            </div>
            <div class="rt-grid-2">
                <div><label>DOI</label><input name="doi" maxlength="200" value="${esc(s.doi)}"></div>
                <div><label>URL</label><input name="url" maxlength="500" value="${esc(s.url)}"></div>
            </div>
            <div><label>Notes</label><textarea name="notes" maxlength="20000">${esc(s.notes)}</textarea></div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">${submission ? "Save changes" : "Add submission"}</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function publicationStatusForm(submission) {
        const allowed = PUBLICATION_TRANSITIONS[submission.status] || [];
        if (!allowed.length) {
            return `${empty("This submission is in a final state.")}
                <div class="rt-actions"><button class="btn btn-secondary btn-small" type="button" data-action="cancel">Close</button></div>`;
        }
        return `
        <form class="rt-form" data-form="publication-status">
            <h4 style="font-size:14px;">Update submission status</h4>
            <div class="rt-grid-2">
                <div><label>New status</label><select name="status">${options(allowed, allowed[0])}</select></div>
                <div><label>Note</label><input name="note" maxlength="2000"></div>
            </div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Update status</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function publicationRevisionForm() {
        return `
        <form class="rt-form" data-form="publication-revision">
            <h4 style="font-size:14px;">Record a revision</h4>
            <div><label>Revision notes</label><textarea name="notes" required maxlength="10000"></textarea></div>
            <div><label>Submitted date (optional)</label><input name="submitted_at" type="date"></div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Add revision</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function publicationItem(submission) {
        return `
        <div class="rt-item">
            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                <h4>${esc(submission.title)} ${badge(submission.status)}</h4>
                <span class="rt-meta">${esc(VENUE_LABELS[submission.venue_type] || statusLabel(submission.venue_type))}</span>
            </div>
            <div class="rt-meta">
                ${esc(submission.venue || "Venue not set")}
                &middot; latest revision ${submission.latest_revision}
                &middot; updated ${fmtDate(submission.updated_at)}
            </div>
            <div class="rt-actions">
                <button class="btn btn-secondary btn-small" type="button" data-action="open" data-id="${submission.id}">Open</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="delete" data-id="${submission.id}">Delete</button>
            </div>
        </div>`;
    }

    function publicationDetailHTML(submission) {
        const revisions = submission.revisions.length
            ? `<div class="rt-list">${submission.revisions.map(revision => `
                <div class="rt-item">
                    <h4>Revision ${revision.revision_number}</h4>
                    <div class="rt-meta">submitted ${fmtDate(revision.submitted_at)} &middot; recorded ${fmtDate(revision.created_at)}</div>
                    ${pre(revision.notes)}
                </div>`).join("")}</div>`
            : empty("No revisions recorded.");

        const history = submission.history.length
            ? `<div class="rt-list">${submission.history.map(event => `
                <div class="rt-item">
                    <div class="rt-meta">${fmtDate(event.created_at)} &middot; ${esc(event.actor_name || "System")}</div>
                    <div>${esc(statusLabel(event.from_status || "—"))} → ${esc(statusLabel(event.to_status))}${event.note ? ` — ${esc(event.note)}` : ""}</div>
                </div>`).join("")}</div>`
            : empty("No status history yet.");

        const canRecordRevision = PUBLICATION_REVISION_STATUSES.indexOf(submission.status) !== -1;

        return `
        <div class="rt-detail">
            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                <h3>${esc(submission.title)} ${badge(submission.status)}</h3>
                <span class="rt-meta">${esc(VENUE_LABELS[submission.venue_type] || statusLabel(submission.venue_type))}</span>
            </div>
            <p class="rt-meta">
                ${esc(submission.venue || "Venue not set")}
                ${submission.doi ? ` &middot; DOI ${esc(submission.doi)}` : ""}
                ${submission.url ? ` &middot; ${link(submission.url, "Manuscript link")}` : ""}
            </p>
            <div class="rt-meta">
                Submitted ${fmtDate(submission.submitted_at)}
                &middot; decision ${fmtDate(submission.decision_at)}
                &middot; published ${fmtDate(submission.published_at)}
            </div>
            ${pre(submission.notes)}
            <div class="rt-actions">
                <button class="btn btn-secondary btn-small" type="button" data-action="meta-edit">Edit submission</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="status-edit">Update status</button>
            </div>
        </div>

        <h4 style="margin-top:18px;font-size:14px;">Revisions</h4>
        ${revisions}
        ${canRecordRevision
            ? `<button class="btn btn-secondary btn-small" type="button" data-action="revision-new">Record revision</button>`
            : `<p class="rt-meta">Revisions can be recorded once the manuscript is submitted.</p>`}

        <h4 style="margin-top:18px;font-size:14px;">Status history</h4>
        ${history}`;
    }

    async function renderPublicationDetail(container) {
        const st = viewState(container);
        const submissionId = st.detailId;
        shell(container, VIEWS["rt20-publications"], `
            <button class="btn btn-secondary btn-small" type="button" data-action="back">
                <i class="fa-solid fa-arrow-left"></i> Back to publications
            </button>`);
        setStatus(container, "Loading submission…");
        const submission = await client().getPublication(submissionId, {
            revision_limit: 200,
            history_limit: 200
        });
        cached(container, "detail", submission);
        setBody(container, publicationDetailHTML(submission));
        setStatus(container, `${submission.revisions_total} revision(s), ${submission.history_total} history event(s).`);
    }

    defineView({
        id: "rt20-publications",
        title: "Publications",
        icon: "fa-book",
        roles: ["student", "faculty", "admin"],
        note: "Track manuscript submissions, status transitions and revision rounds.",
        render(container) {
            const st = viewState(container, { detailId: null, status: "" });
            if (st.detailId) return renderPublicationDetail(container);
            shell(container, VIEWS["rt20-publications"], `
                <select name="pubStatus">${options([""].concat(PUBLICATION_STATUSES), st.status, { "": "All statuses" })}</select>
                <button type="button" class="btn btn-secondary btn-small" data-action="apply">Apply</button>
                <button type="button" class="btn btn-small" data-action="new"><i class="fa-solid fa-plus"></i> New submission</button>
            `);
            setStatus(container, "Loading submissions…");
            return client().listPublications({
                status: st.status || undefined,
                limit: 100
            }).then(payload => {
                const submissions = Array.isArray(payload.submissions) ? payload.submissions : [];
                setBody(container, submissions.length
                    ? `<div class="rt-list">${submissions.map(publicationItem).join("")}</div>`
                    : empty("No publication submissions match this filter."));
                setStatus(container, `Showing ${submissions.length} of ${payload.total != null ? payload.total : submissions.length} submissions.`);
            });
        },
        actions: {
            apply(container) {
                const st = viewState(container);
                st.status = field(container, "pubStatus");
                closeEditor(container);
                return reload(container);
            },
            new(container) {
                openEditor(container, publicationForm(null));
            },
            open(container, element) {
                viewState(container).detailId = dataId(element);
                closeEditor(container);
                return reload(container);
            },
            back(container) {
                viewState(container).detailId = null;
                closeEditor(container);
                return reload(container);
            },
            async delete(container, element) {
                const id = dataId(element);
                if (!id) return;
                if (!global.confirm || !global.confirm("Delete this publication submission, its revisions and history?")) return;
                await client().deletePublication(id);
                await afterWrite(container, "Submission deleted.");
            },
            "meta-edit"(container) {
                const detail = cached(container, "detail");
                if (detail) openEditor(container, publicationForm(detail));
            },
            "status-edit"(container) {
                const detail = cached(container, "detail");
                if (detail) openEditor(container, publicationStatusForm(detail));
            },
            "revision-new"(container) {
                openEditor(container, publicationRevisionForm());
            },
            cancel(container) {
                closeEditor(container);
            }
        },
        forms: {
            async publication(container, form) {
                const id = field(form, "submission_id");
                const payload = {
                    title: field(form, "title"),
                    venue: field(form, "venue"),
                    venue_type: field(form, "venue_type") || "journal",
                    doi: field(form, "doi"),
                    url: field(form, "url"),
                    notes: field(form, "notes")
                };
                if (id) {
                    await client().updatePublication(Number(id), payload);
                    await afterWrite(container, "Submission saved.");
                } else {
                    const created = await client().createPublication(payload);
                    viewState(container).detailId = created.id;
                    await afterWrite(container, "Submission added.");
                }
            },
            async "publication-status"(container, form) {
                const detail = cached(container, "detail");
                if (!detail) return;
                await client().updatePublicationStatus(detail.id, {
                    status: field(form, "status"),
                    note: field(form, "note")
                });
                await afterWrite(container, "Submission status updated.");
            },
            async "publication-revision"(container, form) {
                const detail = cached(container, "detail");
                if (!detail) return;
                const submitted = epochFromDate(field(form, "submitted_at"));
                const payload = { notes: field(form, "notes") };
                if (submitted) payload.submitted_at = submitted;
                await client().addPublicationRevision(detail.id, payload);
                await afterWrite(container, "Revision recorded.");
            }
        }
    });

    function splitList(text) {
        return String(text || "").split(/[,;\n]/).map(item => item.trim()).filter(Boolean);
    }

    function signalChips(signals) {
        const entries = Object.entries(signals || {}).filter(([, value]) => Number.isFinite(Number(value)));
        if (!entries.length) return "";
        return `<div class="rt-chips">${entries.map(([key, value]) =>
            `<span class="rt-chip">${esc(statusLabel(key))}: ${Number(value).toFixed(3)}</span>`).join("")}</div>`;
    }

    function scoreBadge(score) {
        const numeric = Number(score);
        if (!Number.isFinite(numeric)) return "";
        return `<span class="rt-badge rt-badge-open">${(numeric * 100).toFixed(0)}% match</span>`;
    }

    /* --------------------------------------------------
     * RESEARCH OPPORTUNITIES
     * -------------------------------------------------- */

    const OPPORTUNITY_CATEGORIES = ["research", "funding"];
    const OPPORTUNITY_STATUSES = ["draft", "open", "closed"];

    function opportunityForm(opportunity, role) {
        const o = opportunity || {};
        const categories = role === "admin" ? OPPORTUNITY_CATEGORIES : ["research"];
        return `
        <form class="rt-form" data-form="opportunity">
            <h4 style="font-size:14px;">${opportunity ? "Edit opportunity" : "New opportunity"}</h4>
            <input type="hidden" name="opportunity_id" value="${opportunity ? opportunity.id : ""}">
            <div class="rt-grid-2">
                <div><label>Category</label><select name="category"${opportunity ? " disabled" : ""}>${options(categories, o.category || "research")}</select></div>
                <div><label>Status</label><select name="status">${options(OPPORTUNITY_STATUSES, o.status || "open")}</select></div>
            </div>
            <div><label>Title</label><input name="title" required maxlength="200" value="${esc(o.title)}"></div>
            <div><label>Description</label><textarea name="description" maxlength="10000">${esc(o.description)}</textarea></div>
            <div class="rt-grid-2">
                <div><label>Organization</label><input name="organization" maxlength="200" value="${esc(o.organization)}"></div>
                <div><label>Location</label><input name="location" maxlength="150" value="${esc(o.location)}"></div>
            </div>
            <div class="rt-grid-2">
                <div><label>URL</label><input name="url" maxlength="300" value="${esc(o.url)}"></div>
                <div><label>Deadline</label><input name="deadline_at" type="date" value="${isoDate(o.deadline_at)}"></div>
            </div>
            <div><label>Required skills</label><input name="required_skills" maxlength="4000" value="${esc(o.required_skills)}"></div>
            <div><label>Required research areas</label><input name="required_research_areas" maxlength="4000" value="${esc(o.required_research_areas)}"></div>
            <div><label>Required expertise</label><input name="required_expertise" maxlength="4000" value="${esc(o.required_expertise)}"></div>
            <div><label>Eligibility notes</label><textarea name="eligibility" maxlength="4000">${esc(o.eligibility)}</textarea></div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">${opportunity ? "Save changes" : "Publish opportunity"}</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function opportunityUpdatePayload(form) {
        return {
            status: field(form, "status") || "open",
            title: field(form, "title"),
            description: field(form, "description"),
            organization: field(form, "organization"),
            location: field(form, "location"),
            url: field(form, "url"),
            deadline_at: epochFromDate(field(form, "deadline_at")),
            required_skills: field(form, "required_skills"),
            required_research_areas: field(form, "required_research_areas"),
            required_expertise: field(form, "required_expertise"),
            eligibility: field(form, "eligibility")
        };
    }

    function opportunityCreatePayload(form) {
        return {
            category: field(form, "category") || "research",
            status: field(form, "status") || "open",
            title: field(form, "title"),
            description: field(form, "description"),
            organization: field(form, "organization"),
            location: field(form, "location"),
            url: field(form, "url"),
            deadline_at: epochFromDate(field(form, "deadline_at")),
            required_skills: field(form, "required_skills"),
            required_research_areas: field(form, "required_research_areas"),
            required_expertise: field(form, "required_expertise"),
            eligibility: field(form, "eligibility")
        };
    }

    function opportunityItem(opportunity, context) {
        const open = Boolean(opportunity.is_open);
        return `
        <div class="rt-item">
            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                <h4>${esc(opportunity.title)} ${badge(opportunity.status)}
                    <span class="rt-badge">${esc(statusLabel(opportunity.category))}</span></h4>
                <span class="rt-meta">${open ? "Open" : "Closed"}</span>
            </div>
            <div class="rt-meta">
                ${esc(opportunity.organization || "Organization not listed")}
                ${opportunity.location ? ` &middot; ${esc(opportunity.location)}` : ""}
                &middot; deadline ${opportunity.deadline_at ? fmtDate(opportunity.deadline_at) : "not set"}
            </div>
            ${pre(opportunity.description)}
            ${chips(splitList(opportunity.required_skills))}
            <div class="rt-actions">
                ${context.student ? `<button class="btn btn-secondary btn-small" type="button" data-action="eligibility" data-id="${opportunity.id}">Check eligibility</button>` : ""}
                ${context.student && open ? `<button class="btn btn-small" type="button" data-action="apply" data-id="${opportunity.id}">Apply</button>` : ""}
                ${context.manage ? `<button class="btn btn-secondary btn-small" type="button" data-action="edit" data-id="${opportunity.id}">Edit</button>` : ""}
                ${context.manage ? `<button class="btn btn-secondary btn-small" type="button" data-action="applications" data-id="${opportunity.id}">Applications</button>` : ""}
                ${context.manage ? `<button class="btn btn-secondary btn-small" type="button" data-action="delete" data-id="${opportunity.id}">Delete</button>` : ""}
                ${opportunity.url ? `<span class="rt-meta">${link(opportunity.url, "Open listing")}</span>` : ""}
            </div>
        </div>`;
    }

    function opportunityMatchItem(match) {
        const opportunity = match.opportunity || {};
        const summary = match.eligibility
            ? (match.eligibility.eligible === true ? "Eligible"
                : match.eligibility.eligible === false ? "Not eligible"
                : "Eligibility unknown")
            : "";
        return `
        <div class="rt-item">
            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                <h4>${esc(opportunity.title)} ${scoreBadge(match.match_score)}</h4>
                <span class="rt-meta">${esc(summary)}</span>
            </div>
            <div class="rt-meta">
                ${esc(opportunity.organization || "")}
                &middot; deadline ${opportunity.deadline_at ? fmtDate(opportunity.deadline_at) : "not set"}
            </div>
            ${signalChips(match.signals)}
            <div class="rt-actions">
                ${opportunity.is_open
                    ? `<button class="btn btn-small" type="button" data-action="apply" data-id="${opportunity.id}">Apply</button>`
                    : `<span class="rt-meta">This opportunity is closed.</span>`}
            </div>
        </div>`;
    }

    function applicationDecisionItem(application) {
        return `
        <div class="rt-item">
            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                <h4>${esc(application.student_full_name || `User ${application.student_user_id}`)} ${badge(application.status)}</h4>
                <span class="rt-meta">${esc(application.student_email || "")}</span>
            </div>
            <div class="rt-meta">applied ${fmtDate(application.created_at)}</div>
            ${pre(application.message)}
            ${application.status === "pending" ? `<div class="rt-actions">
                <button class="btn btn-small" type="button" data-action="accept" data-id="${application.id}">Accept</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="reject" data-id="${application.id}">Reject</button>
            </div>` : (application.decision_note ? pre(application.decision_note) : "")}
        </div>`;
    }

    async function renderOpportunityApplications(container) {
        const st = viewState(container);
        const opportunity = findById(cached(container, "opportunities") || [], st.manageId);
        shell(container, VIEWS["rt20-opportunities"], `
            <button class="btn btn-secondary btn-small" type="button" data-action="back">
                <i class="fa-solid fa-arrow-left"></i> Back to opportunities
            </button>`);
        setStatus(container, "Loading applications…");
        const payload = await client().listOpportunityApplications(st.manageId, { limit: 200 });
        const applications = Array.isArray(payload.applications) ? payload.applications : [];
        setBody(container, `
            <h3 style="font-size:15px;">${esc(opportunity ? opportunity.title : "Opportunity")} applications</h3>
            ${applications.length
                ? `<div class="rt-list">${applications.map(applicationDecisionItem).join("")}</div>`
                : empty("No applications yet.")}`);
        setStatus(container, `${applications.length} application(s).`);
    }

    defineView({
        id: "rt20-opportunities",
        title: "Opportunities",
        icon: "fa-bullhorn",
        roles: ["student", "faculty", "admin"],
        note: "Research and funding opportunities with eligibility, matching and application tracking.",
        render(container) {
            const user = currentUser() || { role: "student" };
            const st = viewState(container, {
                q: "", category: "", scope: "all", matches: null, manageId: null
            });
            if (st.manageId) return renderOpportunityApplications(container);

            const canManage = user.role === "faculty" || user.role === "admin";
            const isStudent = user.role === "student";
            shell(container, VIEWS["rt20-opportunities"], `
                <input type="search" name="oppQ" value="${esc(st.q)}" maxlength="200" placeholder="Search opportunities…">
                <select name="oppCategory">${options([""].concat(OPPORTUNITY_CATEGORIES), st.category, { "": "All categories" })}</select>
                ${canManage ? `<select name="oppScope">${options(["all", "mine"], st.scope, { all: "All opportunities", mine: "My opportunities" })}</select>` : ""}
                <button type="button" class="btn btn-secondary btn-small" data-action="apply-filter">Apply</button>
                ${isStudent ? `<button type="button" class="btn btn-secondary btn-small" data-action="match">Find matches</button>` : ""}
                ${canManage ? `<button type="button" class="btn btn-small" data-action="new"><i class="fa-solid fa-plus"></i> New opportunity</button>` : ""}
            `);
            setStatus(container, "Loading opportunities…");
            const params = { q: st.q || undefined, category: st.category || undefined, limit: 100 };
            const request = canManage && st.scope === "mine"
                ? client().listMyOpportunities(params)
                : client().searchOpportunities(params);
            return request.then(payload => {
                const opportunities = Array.isArray(payload.opportunities) ? payload.opportunities : [];
                cached(container, "opportunities", opportunities);
                const context = { student: isStudent, manage: canManage && st.scope === "mine" };
                const matches = Array.isArray(st.matches) ? st.matches : null;
                setBody(container, `
                    ${matches ? `<h4 style="font-size:14px;">Recommended matches</h4>
                        <div class="rt-list">${matches.map(opportunityMatchItem).join("")}</div>` : ""}
                    <h4 style="font-size:14px;">${context.manage ? "My opportunities" : "Opportunities"}</h4>
                    ${opportunities.length
                        ? `<div class="rt-list">${opportunities.map(item => opportunityItem(item, context)).join("")}</div>`
                        : empty("No opportunities match this filter.")}`);
                setStatus(container, `Showing ${opportunities.length} of ${payload.total != null ? payload.total : opportunities.length} opportunities.`);
            });
        },
        actions: {
            "apply-filter"(container) {
                const st = viewState(container);
                st.q = field(container, "oppQ");
                st.category = field(container, "oppCategory");
                const scope = container.querySelector('[name="oppScope"]');
                if (scope) st.scope = scope.value;
                if (st.scope !== "mine") st.matches = null;
                closeEditor(container);
                return reload(container);
            },
            async match(container) {
                const st = viewState(container);
                setStatus(container, "Scoring opportunities against your student profile…");
                const payload = await client().matchOpportunities({
                    category: st.category || "research",
                    top_k: 5,
                    eligible_only: false
                });
                st.matches = Array.isArray(payload.matches) ? payload.matches : [];
                return reload(container);
            },
            new(container) {
                const user = currentUser() || {};
                openEditor(container, opportunityForm(null, user.role));
            },
            edit(container, element) {
                const opportunity = findById(cached(container, "opportunities") || [], dataId(element));
                if (!opportunity) return;
                const user = currentUser() || {};
                openEditor(container, opportunityForm(opportunity, user.role));
            },
            "applications"(container, element) {
                viewState(container).manageId = dataId(element);
                closeEditor(container);
                return reload(container);
            },
            back(container) {
                viewState(container).manageId = null;
                closeEditor(container);
                return reload(container);
            },
            async delete(container, element) {
                const id = dataId(element);
                if (!id) return;
                if (!global.confirm || !global.confirm("Delete this opportunity and all its applications?")) return;
                await client().deleteOpportunity(id);
                await afterWrite(container, "Opportunity deleted.");
            },
            async eligibility(container, element) {
                const id = dataId(element);
                if (!id) return;
                const result = await client().getOpportunityEligibility(id);
                const label = result.eligible === true ? "Eligible"
                    : result.eligible === false ? "Not eligible" : "Eligibility unknown";
                openEditor(container, `
                    <div class="rt-detail">
                        <h4>Eligibility result</h4>
                        <p>${esc(label)} ${badge(result.status)}</p>
                        ${chips((result.matched_skills || []).map(skill => `✓ ${skill}`))}
                        ${chips((result.missing_skills || []).map(skill => `+ ${skill}`))}
                        ${(result.reasons || []).length
                            ? `<ul class="rt-meta">${result.reasons.map(reason => `<li>${esc(reason)}</li>`).join("")}</ul>`
                            : ""}
                        <div class="rt-actions">
                            <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Close</button>
                        </div>
                    </div>`);
            },
            apply(container, element) {
                const id = dataId(element);
                if (!id) return;
                openEditor(container, `
                    <form class="rt-form" data-form="opportunity-apply">
                        <h4 style="font-size:14px;">Apply to this opportunity</h4>
                        <input type="hidden" name="opportunity_id" value="${id}">
                        <div><label>Message to the opportunity owner</label><textarea name="message" required maxlength="2000"></textarea></div>
                        <div class="rt-actions">
                            <button class="btn btn-small" type="submit">Submit application</button>
                            <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
                        </div>
                    </form>`);
            },
            async accept(container, element) {
                const st = viewState(container);
                const applicationId = dataId(element);
                if (!st.manageId || !applicationId) return;
                await client().decideOpportunityApplication(st.manageId, applicationId, { decision: "accept", note: "" });
                await afterWrite(container, "Application accepted.");
            },
            async reject(container, element) {
                const st = viewState(container);
                const applicationId = dataId(element);
                if (!st.manageId || !applicationId) return;
                await client().decideOpportunityApplication(st.manageId, applicationId, { decision: "reject", note: "" });
                await afterWrite(container, "Application rejected.");
            },
            cancel(container) {
                closeEditor(container);
            }
        },
        forms: {
            async opportunity(container, form) {
                const id = field(form, "opportunity_id");
                if (id) {
                    await client().updateOpportunity(Number(id), opportunityUpdatePayload(form));
                    await afterWrite(container, "Opportunity saved.");
                } else {
                    await client().createOpportunity(opportunityCreatePayload(form));
                    await afterWrite(container, "Opportunity published.");
                }
            },
            async "opportunity-apply"(container, form) {
                await client().applyToOpportunity(Number(field(form, "opportunity_id")), {
                    message: field(form, "message")
                });
                await afterWrite(container, "Application submitted.");
            }
        }
    });

    /* --------------------------------------------------
     * MY APPLICATIONS
     * -------------------------------------------------- */

    defineView({
        id: "rt20-applications",
        title: "My Applications",
        icon: "fa-paper-plane",
        roles: ["student"],
        note: "Status of your research and funding applications, with withdrawal for pending ones.",
        render(container) {
            shell(container, VIEWS["rt20-applications"], `
                <button class="btn btn-secondary btn-small" type="button" data-action="refresh">Refresh</button>`);
            setStatus(container, "Loading applications…");
            return client().listMyApplications({ limit: 200 }).then(payload => {
                const applications = Array.isArray(payload.applications) ? payload.applications : [];
                setBody(container, applications.length
                    ? `<div class="rt-list">${applications.map(application => {
                        const opportunity = application.opportunity || {};
                        return `
                        <div class="rt-item">
                            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                                <h4>${esc(opportunity.title || `Opportunity ${application.opportunity_id}`)} ${badge(application.status)}</h4>
                                <span class="rt-meta">${esc(statusLabel(opportunity.category))}</span>
                            </div>
                            <div class="rt-meta">
                                ${esc(opportunity.organization || "")}
                                &middot; deadline ${opportunity.deadline_at ? fmtDate(opportunity.deadline_at) : "not set"}
                                &middot; applied ${fmtDate(application.created_at)}
                            </div>
                            ${pre(application.message)}
                            ${application.decision_note ? pre(application.decision_note) : ""}
                            <div class="rt-actions">
                                ${application.status === "pending"
                                    ? `<button class="btn btn-secondary btn-small" type="button" data-action="withdraw" data-id="${application.opportunity_id}">Withdraw</button>`
                                    : `<span class="rt-meta">Decision recorded ${fmtDate(application.reviewed_at)}.</span>`}
                            </div>
                        </div>`;
                    }).join("")}</div>`
                    : empty("You have not applied to an opportunity yet."));
                setStatus(container, `${applications.length} application(s).`);
            });
        },
        actions: {
            refresh(container) {
                closeEditor(container);
                return reload(container);
            },
            async withdraw(container, element) {
                const id = dataId(element);
                if (!id) return;
                if (!global.confirm || !global.confirm("Withdraw this pending application?")) return;
                await client().withdrawMyApplication(id);
                await afterWrite(container, "Application withdrawn.");
            }
        }
    });

    /* --------------------------------------------------
     * RESEARCH TEAMS
     * -------------------------------------------------- */

    function teamCreateForm() {
        return `
        <form class="rt-form" data-form="team-create">
            <h4 style="font-size:14px;">New research team</h4>
            <div><label>Team name</label><input name="name" required maxlength="120"></div>
            <div><label>Description</label><textarea name="description" maxlength="4000"></textarea></div>
            <div class="rt-grid-2">
                <div><label>Research areas</label><textarea name="research_areas" maxlength="4000"></textarea></div>
                <div><label>Expertise</label><textarea name="expertise" maxlength="4000"></textarea></div>
                <div><label>Skills</label><textarea name="skills" maxlength="4000"></textarea></div>
                <div><label>Projects</label><textarea name="projects" maxlength="4000"></textarea></div>
            </div>
            <div><label>Publications</label><textarea name="publications" maxlength="4000"></textarea></div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Create team</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function teamInviteForm() {
        return `
        <form class="rt-form" data-form="team-invite">
            <h4 style="font-size:14px;">Invite a member</h4>
            <div><label>User ID</label><input name="user_id" type="number" min="1" required></div>
            <p class="rt-meta">Only active student or faculty accounts can join a research team.</p>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Send invitation</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function teamDetailHTML(team) {
        const user = currentUser() || {};
        const isOwner = team.role === "owner";
        const focusHTML = Object.entries(team.focus || {})
            .filter(([, value]) => String(value || "").trim())
            .map(([name, value]) => `
                <div class="rt-item">
                    <div class="rt-meta">${esc(statusLabel(name))}</div>
                    <div>${esc(value)}</div>
                </div>`).join("");

        const membersHTML = team.members.map(member => `
            <div class="rt-item">
                <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                    <h4>${esc(member.full_name || `User ${member.user_id}`)} ${badge(member.role)}</h4>
                    <span class="rt-meta">joined ${fmtDate(member.joined_at)}</span>
                </div>
                ${isOwner && member.role !== "owner" ? `<div class="rt-actions">
                    <button class="btn btn-secondary btn-small" type="button" data-action="member-remove" data-user="${member.user_id}">Remove</button>
                </div>` : ""}
            </div>`).join("");

        const invitationsHTML = (team.invitations || []).length
            ? `<h4 style="margin-top:18px;font-size:14px;">Pending invitations</h4>
                <div class="rt-list">${team.invitations.map(invitation => `
                    <div class="rt-item">
                        <div class="rt-meta">User ${invitation.invited_user_id} &middot; invited ${fmtDate(invitation.created_at)}</div>
                    </div>`).join("")}</div>`
            : "";

        return `
        <div class="rt-detail">
            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                <h3>${esc(team.name)}</h3>
                <span class="rt-meta">${esc(statusLabel(team.role))}</span>
            </div>
            ${pre(team.description)}
            <div class="rt-actions">
                <button class="btn btn-secondary btn-small" type="button" data-action="recommend">Recommend researchers</button>
                ${isOwner ? `<button class="btn btn-secondary btn-small" type="button" data-action="invite">Invite member</button>` : ""}
                ${isOwner ? `<button class="btn btn-secondary btn-small" type="button" data-action="delete-team">Delete team</button>` : ""}
            </div>
        </div>

        <h4 style="margin-top:18px;font-size:14px;">Research focus</h4>
        ${focusHTML || empty("No research focus recorded yet.")}

        <h4 style="margin-top:18px;font-size:14px;">Members</h4>
        <div class="rt-list">${membersHTML}</div>
        ${isOwner && user.id === team.owner_user_id ? invitationsHTML : ""}`;
    }

    defineView({
        id: "rt20-teams",
        title: "Research Teams",
        icon: "fa-people-group",
        roles: ["student", "faculty"],
        note: "Form teams around a shared research focus, invite members and get researcher recommendations.",
        render(container) {
            const st = viewState(container, { detailId: null });
            if (st.detailId) return renderTeamDetail(container);
            shell(container, VIEWS["rt20-teams"], `
                <button class="btn btn-small" type="button" data-action="new"><i class="fa-solid fa-plus"></i> New team</button>`);
            setStatus(container, "Loading teams…");
            return client().listMyTeams().then(payload => {
                const teams = Array.isArray(payload.teams) ? payload.teams : [];
                const invitations = Array.isArray(payload.invitations) ? payload.invitations : [];
                const invitationHTML = invitations.length
                    ? `<h4 style="font-size:14px;">Pending invitations</h4>
                        <div class="rt-list">${invitations.map(invitation => `
                            <div class="rt-item">
                                <h4>${esc(invitation.team_name)}</h4>
                                <div class="rt-meta">invited ${fmtDate(invitation.created_at)}</div>
                                <div class="rt-actions">
                                    <button class="btn btn-small" type="button" data-action="invitation-accept"
                                            data-id="${invitation.id}" data-team="${invitation.team_id}">Accept</button>
                                    <button class="btn btn-secondary btn-small" type="button" data-action="invitation-decline"
                                            data-id="${invitation.id}" data-team="${invitation.team_id}">Decline</button>
                                </div>
                            </div>`).join("")}</div>`
                    : "";
                const teamHTML = teams.length
                    ? teams.map(team => `
                        <div class="rt-item">
                            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                                <h4>${esc(team.name)}</h4>
                                <span class="rt-meta">${esc(statusLabel(team.role))} &middot; ${team.member_count} member(s)</span>
                            </div>
                            <div class="rt-actions">
                                <button class="btn btn-secondary btn-small" type="button" data-action="open" data-id="${team.id}">Open</button>
                            </div>
                        </div>`).join("")
                    : empty("You are not in a research team yet. Create one to get started.");
                setBody(container, `${invitationHTML}<h4 style="margin-top:18px;font-size:14px;">My teams</h4>
                    <div class="rt-list">${teamHTML}</div>`);
                setStatus(container, `${teams.length} team(s), ${invitations.length} pending invitation(s).`);
            });
        },
        actions: {
            new(container) {
                openEditor(container, teamCreateForm());
            },
            open(container, element) {
                viewState(container).detailId = dataId(element);
                closeEditor(container);
                return reload(container);
            },
            back(container) {
                viewState(container).detailId = null;
                closeEditor(container);
                return reload(container);
            },
            async "invitation-accept"(container, element) {
                const invitationId = dataId(element);
                const teamId = dataNumber(element, "team");
                if (!invitationId || !teamId) return;
                await client().decideTeamInvitation(teamId, invitationId, { decision: "accept" });
                await afterWrite(container, "Invitation accepted.");
            },
            async "invitation-decline"(container, element) {
                const invitationId = dataId(element);
                const teamId = dataNumber(element, "team");
                if (!invitationId || !teamId) return;
                await client().decideTeamInvitation(teamId, invitationId, { decision: "decline" });
                await afterWrite(container, "Invitation declined.");
            },
            invite(container) {
                openEditor(container, teamInviteForm());
            },
            async "member-remove"(container, element) {
                const st = viewState(container);
                const userId = dataNumber(element, "user");
                if (!st.detailId || !userId) return;
                if (!global.confirm || !global.confirm("Remove this member from the team?")) return;
                await client().removeTeamMember(st.detailId, userId);
                await afterWrite(container, "Member removed.");
            },
            async "delete-team"(container) {
                const st = viewState(container);
                if (!st.detailId) return;
                if (!global.confirm || !global.confirm("Delete this team and all its invitations?")) return;
                await client().deleteTeam(st.detailId);
                st.detailId = null;
                await afterWrite(container, "Team deleted.");
            },
            async recommend(container) {
                const st = viewState(container);
                if (!st.detailId) return;
                setStatus(container, "Scoring researchers against the team focus…");
                const payload = await client().getTeamRecommendations(st.detailId, { top_k: 5 });
                const recommendations = Array.isArray(payload.recommendations) ? payload.recommendations : [];
                openEditor(container, `
                    <div class="rt-detail">
                        <h4>Recommended researchers</h4>
                        ${recommendations.length
                            ? `<div class="rt-list">${recommendations.map(item => `
                                <div class="rt-item">
                                    <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                                        <h4>${esc(item.name)} ${scoreBadge(item.match_score)}</h4>
                                        <span class="rt-meta">${esc(item.department || "Department not specified")}</span>
                                    </div>
                                    ${pre((item.explanation || {}).summary || "")}
                                    ${chips((item.matched_skills || []).map(skill => `✓ ${skill}`))}
                                    ${chips((item.skill_gap || []).map(skill => `+ ${skill}`))}
                                </div>`).join("")}</div>`
                            : empty("No researchers matched this team's focus.")}
                        <div class="rt-actions">
                            <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Close</button>
                        </div>
                    </div>`);
                setStatus(container, `${recommendations.length} recommendation(s) from ${payload.total_candidates || 0} candidates.`);
            },
            cancel(container) {
                closeEditor(container);
            }
        },
        forms: {
            async "team-create"(container, form) {
                await client().createTeam({
                    name: field(form, "name"),
                    description: field(form, "description"),
                    research_areas: field(form, "research_areas"),
                    expertise: field(form, "expertise"),
                    skills: field(form, "skills"),
                    projects: field(form, "projects"),
                    publications: field(form, "publications")
                });
                await afterWrite(container, "Team created.");
            },
            async "team-invite"(container, form) {
                const st = viewState(container);
                if (!st.detailId) return;
                await client().inviteToTeam(st.detailId, {
                    user_id: Number(field(form, "user_id"))
                });
                await afterWrite(container, "Invitation sent.");
            }
        }
    });

    async function renderTeamDetail(container) {
        const st = viewState(container);
        shell(container, VIEWS["rt20-teams"], `
            <button class="btn btn-secondary btn-small" type="button" data-action="back">
                <i class="fa-solid fa-arrow-left"></i> Back to teams
            </button>`);
        setStatus(container, "Loading team…");
        const team = await client().getTeam(st.detailId);
        cached(container, "detail", team);
        setBody(container, teamDetailHTML(team));
        setStatus(container, `${team.members.length} member(s).`);
    }

    /* --------------------------------------------------
     * RESEARCH WORKSPACES
     * -------------------------------------------------- */

    function workspaceTaskForm(members) {
        return `
        <form class="rt-form" data-form="workspace-task">
            <h4 style="font-size:14px;">New task</h4>
            <div><label>Title</label><input name="title" required maxlength="200"></div>
            <div><label>Description</label><textarea name="description" maxlength="4000"></textarea></div>
            <div class="rt-grid-2">
                <div><label>Assignee</label><select name="assignee_user_id"><option value="">Unassigned</option>${members.map(member =>
                    `<option value="${member.user_id}">${esc(member.full_name)}</option>`).join("")}</select></div>
                <div><label>Due date</label><input name="due_at" type="date"></div>
            </div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Add task</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function workspaceCommentForm(tasks) {
        return `
        <form class="rt-form" data-form="workspace-comment">
            <h4 style="font-size:14px;">New comment</h4>
            <div><label>Comment</label><textarea name="body" required maxlength="4000"></textarea></div>
            <div><label>Attach to task</label><select name="task_id"><option value="">Workspace-wide</option>${tasks.map(task =>
                `<option value="${task.id}">${esc(task.title)}</option>`).join("")}</select></div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Post comment</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function workspaceMilestoneForm() {
        return `
        <form class="rt-form" data-form="workspace-milestone">
            <h4 style="font-size:14px;">New milestone</h4>
            <div class="rt-grid-2">
                <div><label>Title</label><input name="title" required maxlength="200"></div>
                <div><label>Due date</label><input name="due_at" type="date"></div>
            </div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Add milestone</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function workspaceDetailHTML(workspace, tasks, comments, milestones) {
        const user = currentUser() || {};
        const isOwner = workspace.role === "owner";
        const memberNames = {};
        (workspace.members || []).forEach(member => { memberNames[member.user_id] = member.full_name; });

        const taskHTML = tasks.length
            ? `<div class="rt-list">${tasks.map(task => {
                const nextStatus = task.status === "todo" ? "in_progress"
                    : task.status === "in_progress" ? "done" : "todo";
                const label = task.status === "todo" ? "Start" : task.status === "in_progress" ? "Complete" : "Reopen";
                const canDelete = isOwner || task.created_by_user_id === user.id;
                return `
                <div class="rt-item">
                    <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                        <h4>${esc(task.title)} ${badge(task.status)}</h4>
                        <span class="rt-meta">due ${fmtDate(task.due_at)}</span>
                    </div>
                    ${pre(task.description)}
                    <div class="rt-meta">assignee: ${esc(memberNames[task.assignee_user_id] || "unassigned")}</div>
                    <div class="rt-actions">
                        <button class="btn btn-secondary btn-small" type="button" data-action="task-status"
                                data-id="${task.id}" data-status="${nextStatus}">${label}</button>
                        ${canDelete ? `<button class="btn btn-secondary btn-small" type="button" data-action="task-delete" data-id="${task.id}">Delete</button>` : ""}
                    </div>
                </div>`;
            }).join("")}</div>`
            : empty("No tasks yet.");

        const commentHTML = comments.length
            ? `<div class="rt-list">${comments.map(comment => {
                const canDelete = isOwner || comment.author_user_id === user.id;
                return `
                <div class="rt-item">
                    <div class="rt-meta">${esc(memberNames[comment.author_user_id] || `User ${comment.author_user_id}`)}
                        &middot; ${fmtDate(comment.created_at)}
                        ${comment.task_id ? " &middot; task comment" : ""}</div>
                    ${pre(comment.body)}
                    ${canDelete ? `<div class="rt-actions">
                        <button class="btn btn-secondary btn-small" type="button" data-action="comment-delete" data-id="${comment.id}">Delete</button>
                    </div>` : ""}
                </div>`;
            }).join("")}</div>`
            : empty("No comments yet.");

        const milestoneHTML = milestones.length
            ? `<div class="rt-list">${milestones.map(milestone => {
                const canDelete = isOwner || milestone.created_by_user_id === user.id;
                return `
                <div class="rt-item">
                    <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                        <h4>${esc(milestone.title)} ${badge(milestone.status)}</h4>
                        <span class="rt-meta">due ${fmtDate(milestone.due_at)}</span>
                    </div>
                    <div class="rt-actions">
                        <button class="btn btn-secondary btn-small" type="button" data-action="milestone-status"
                                data-id="${milestone.id}" data-status="${milestone.status === "completed" ? "pending" : "completed"}">
                            ${milestone.status === "completed" ? "Reopen" : "Mark complete"}
                        </button>
                        ${canDelete ? `<button class="btn btn-secondary btn-small" type="button" data-action="milestone-delete" data-id="${milestone.id}">Delete</button>` : ""}
                    </div>
                </div>`;
            }).join("")}</div>`
            : empty("No milestones yet.");

        const memberHTML = (workspace.members || []).map(member => `
            <span class="rt-chip">${esc(member.full_name)} (${esc(statusLabel(member.role))})</span>`).join("");

        return `
        <div class="rt-detail">
            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                <h3>${esc(workspace.title)} ${badge(workspace.status)}</h3>
                <span class="rt-meta">${esc(statusLabel(workspace.role))}</span>
            </div>
            <p class="rt-meta">
                ${workspace.researcher && workspace.researcher.name
                    ? `Researcher: ${esc(workspace.researcher.name)}${workspace.researcher.department ? ` (${esc(workspace.researcher.department)})` : ""}`
                    : "No linked researcher"}
            </p>
            <div class="rt-chips">${memberHTML}</div>
        </div>

        <h4 style="margin-top:18px;font-size:14px;">Tasks</h4>
        ${taskHTML}
        <button class="btn btn-secondary btn-small" type="button" data-action="task-new">Add task</button>

        <h4 style="margin-top:18px;font-size:14px;">Milestones</h4>
        ${milestoneHTML}
        <button class="btn btn-secondary btn-small" type="button" data-action="milestone-new">Add milestone</button>

        <h4 style="margin-top:18px;font-size:14px;">Comments</h4>
        ${commentHTML}
        <button class="btn btn-secondary btn-small" type="button" data-action="comment-new">New comment</button>`;
    }

    async function renderWorkspaceDetail(container) {
        const st = viewState(container);
        shell(container, VIEWS["rt20-workspaces"], `
            <button class="btn btn-secondary btn-small" type="button" data-action="back">
                <i class="fa-solid fa-arrow-left"></i> Back to workspaces
            </button>`);
        setStatus(container, "Loading workspace…");
        const [workspace, taskPayload, commentPayload, milestonePayload] = await Promise.all([
            client().getWorkspace(st.detailId),
            client().listWorkspaceTasks(st.detailId),
            client().listWorkspaceComments(st.detailId, { limit: 100 }),
            client().listWorkspaceMilestones(st.detailId)
        ]);
        const tasks = Array.isArray(taskPayload.tasks) ? taskPayload.tasks : [];
        const comments = Array.isArray(commentPayload.comments) ? commentPayload.comments : [];
        const milestones = Array.isArray(milestonePayload.milestones) ? milestonePayload.milestones : [];
        cached(container, "detail", workspace);
        cached(container, "tasks", tasks);
        setBody(container, workspaceDetailHTML(workspace, tasks, comments, milestones));
        setStatus(container, `${tasks.length} task(s), ${milestones.length} milestone(s), ${comments.length} comment(s).`);
    }

    defineView({
        id: "rt20-workspaces",
        title: "Workspaces",
        icon: "fa-diagram-project",
        roles: ["student", "faculty"],
        note: "Shared collaboration workspaces with tasks, milestones and comments. Workspaces open when a collaboration request is accepted.",
        render(container) {
            const st = viewState(container, { detailId: null });
            if (st.detailId) return renderWorkspaceDetail(container);
            shell(container, VIEWS["rt20-workspaces"], "");
            setStatus(container, "Loading workspaces…");
            return client().listMyWorkspaces().then(payload => {
                const workspaces = Array.isArray(payload.workspaces) ? payload.workspaces : [];
                setBody(container, workspaces.length
                    ? `<div class="rt-list">${workspaces.map(workspace => `
                        <div class="rt-item">
                            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                                <h4>${esc(workspace.title)} ${badge(workspace.status)}</h4>
                                <span class="rt-meta">${esc(statusLabel(workspace.role))} &middot; ${workspace.member_count} member(s)</span>
                            </div>
                            <div class="rt-meta">
                                ${workspace.researcher && workspace.researcher.name
                                    ? `Researcher: ${esc(workspace.researcher.name)}`
                                    : "No linked researcher"}
                                &middot; updated ${fmtDate(workspace.updated_at)}
                            </div>
                            <div class="rt-actions">
                                <button class="btn btn-secondary btn-small" type="button" data-action="open" data-id="${workspace.id}">Open</button>
                            </div>
                        </div>`).join("")}</div>`
                    : empty("No workspaces yet. Accept a collaboration request to create one."));
                setStatus(container, `${workspaces.length} workspace(s).`);
            });
        },
        actions: {
            open(container, element) {
                viewState(container).detailId = dataId(element);
                closeEditor(container);
                return reload(container);
            },
            back(container) {
                viewState(container).detailId = null;
                closeEditor(container);
                return reload(container);
            },
            "task-new"(container) {
                const detail = cached(container, "detail");
                if (detail) openEditor(container, workspaceTaskForm(detail.members || []));
            },
            async "task-status"(container, element) {
                const st = viewState(container);
                const taskId = dataId(element);
                const status = element.getAttribute("data-status");
                if (!st.detailId || !taskId || !status) return;
                await client().updateWorkspaceTask(st.detailId, taskId, { status });
                await afterWrite(container, "Task updated.");
            },
            async "task-delete"(container, element) {
                const st = viewState(container);
                const taskId = dataId(element);
                if (!st.detailId || !taskId) return;
                if (!global.confirm || !global.confirm("Delete this task?")) return;
                await client().deleteWorkspaceTask(st.detailId, taskId);
                await afterWrite(container, "Task deleted.");
            },
            "comment-new"(container) {
                openEditor(container, workspaceCommentForm(cached(container, "tasks") || []));
            },
            async "comment-delete"(container, element) {
                const st = viewState(container);
                const commentId = dataId(element);
                if (!st.detailId || !commentId) return;
                if (!global.confirm || !global.confirm("Delete this comment?")) return;
                await client().deleteWorkspaceComment(st.detailId, commentId);
                await afterWrite(container, "Comment deleted.");
            },
            "milestone-new"(container) {
                openEditor(container, workspaceMilestoneForm());
            },
            async "milestone-status"(container, element) {
                const st = viewState(container);
                const milestoneId = dataId(element);
                const status = element.getAttribute("data-status");
                if (!st.detailId || !milestoneId || !status) return;
                await client().updateWorkspaceMilestone(st.detailId, milestoneId, { status });
                await afterWrite(container, "Milestone updated.");
            },
            async "milestone-delete"(container, element) {
                const st = viewState(container);
                const milestoneId = dataId(element);
                if (!st.detailId || !milestoneId) return;
                if (!global.confirm || !global.confirm("Delete this milestone?")) return;
                await client().deleteWorkspaceMilestone(st.detailId, milestoneId);
                await afterWrite(container, "Milestone deleted.");
            },
            cancel(container) {
                closeEditor(container);
            }
        },
        forms: {
            async "workspace-task"(container, form) {
                const st = viewState(container);
                if (!st.detailId) return;
                const assignee = field(form, "assignee_user_id");
                await client().createWorkspaceTask(st.detailId, {
                    title: field(form, "title"),
                    description: field(form, "description"),
                    assignee_user_id: assignee ? Number(assignee) : null,
                    due_at: epochFromDate(field(form, "due_at"))
                });
                await afterWrite(container, "Task added.");
            },
            async "workspace-comment"(container, form) {
                const st = viewState(container);
                if (!st.detailId) return;
                const taskId = field(form, "task_id");
                await client().createWorkspaceComment(st.detailId, {
                    body: field(form, "body"),
                    task_id: taskId ? Number(taskId) : null
                });
                await afterWrite(container, "Comment posted.");
            },
            async "workspace-milestone"(container, form) {
                const st = viewState(container);
                if (!st.detailId) return;
                await client().createWorkspaceMilestone(st.detailId, {
                    title: field(form, "title"),
                    due_at: epochFromDate(field(form, "due_at"))
                });
                await afterWrite(container, "Milestone added.");
            }
        }
    });

    /* --------------------------------------------------
     * RESEARCH LABS
     * -------------------------------------------------- */

    function labForm(lab) {
        const l = lab || {};
        return `
        <form class="rt-form" data-form="lab">
            <h4 style="font-size:14px;">${lab ? "Edit lab" : "New lab"}</h4>
            <input type="hidden" name="lab_id" value="${lab ? lab.id : ""}">
            <div><label>Lab name</label><input name="name" required maxlength="200" value="${esc(l.name)}"></div>
            <div><label>Description</label><textarea name="description" maxlength="5000">${esc(l.description)}</textarea></div>
            <div><label>Research areas</label><textarea name="research_areas" maxlength="2000">${esc(l.research_areas)}</textarea></div>
            <div><label>Visibility</label><select name="visibility">${options(["public", "institution"], l.visibility || "institution", { public: "Public", institution: "Institution only" })}</select></div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">${lab ? "Save changes" : "Create lab"}</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function labMemberForm() {
        return `
        <form class="rt-form" data-form="lab-member">
            <h4 style="font-size:14px;">Add a lab member</h4>
            <div><label>User ID</label><input name="user_id" type="number" min="1" required></div>
            <p class="rt-meta">Members must already belong to the lab's institution.</p>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Add member</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function labItem(lab) {
        return `
        <div class="rt-item">
            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                <h4>${esc(lab.name)} ${badge(lab.visibility)}</h4>
                <span class="rt-meta">${esc((lab.institution || {}).name || "No institution")}</span>
            </div>
            ${pre(lab.description)}
            ${chips(splitList(lab.research_areas))}
            <div class="rt-meta">${lab.member_count} member(s)${lab.is_member ? " &middot; you are a member" : ""}</div>
            <div class="rt-actions">
                <button class="btn btn-secondary btn-small" type="button" data-action="open" data-id="${lab.id}">Open</button>
            </div>
        </div>`;
    }

    function labDetailHTML(lab) {
        const isOwner = Boolean(lab.is_owner);
        const members = Array.isArray(lab.members) ? lab.members : [];
        const memberHTML = members.length
            ? `<div class="rt-list">${members.map(member => `
                <div class="rt-item">
                    <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                        <h4>${esc(member.full_name)}${member.is_owner ? " (owner)" : ""}</h4>
                        <span class="rt-meta">joined ${fmtDate(member.joined_at)}</span>
                    </div>
                    ${isOwner && !member.is_owner ? `<div class="rt-actions">
                        <button class="btn btn-secondary btn-small" type="button" data-action="member-remove" data-user="${member.user_id}">Remove</button>
                    </div>` : ""}
                </div>`).join("")}</div>`
            : empty(lab.is_member ? "No members yet." : "The roster is visible to lab members only.");

        return `
        <div class="rt-detail">
            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                <h3>${esc(lab.name)} ${badge(lab.visibility)}</h3>
                <span class="rt-meta">${esc((lab.institution || {}).name || "No institution")}</span>
            </div>
            ${pre(lab.description)}
            ${chips(splitList(lab.research_areas))}
            <p class="rt-meta">${lab.member_count} member(s) &middot; created ${fmtDate(lab.created_at)}</p>
            <div class="rt-actions">
                ${isOwner ? `<button class="btn btn-secondary btn-small" type="button" data-action="edit">Edit lab</button>` : ""}
                ${isOwner ? `<button class="btn btn-secondary btn-small" type="button" data-action="member-new">Add member</button>` : ""}
                ${isOwner ? `<button class="btn btn-secondary btn-small" type="button" data-action="delete">Delete lab</button>` : ""}
            </div>
        </div>

        <h4 style="margin-top:18px;font-size:14px;">Members</h4>
        ${memberHTML}`;
    }

    defineView({
        id: "rt20-labs",
        title: "Research Labs",
        icon: "fa-flask",
        roles: ["student", "faculty", "admin"],
        note: "Institution research labs with visibility control, member rosters and ownership.",
        render(container) {
            const user = currentUser() || {};
            const st = viewState(container, { q: "", mine: false, detailId: null });
            if (st.detailId) return renderLabDetail(container);
            const canCreate = user.role === "faculty";
            shell(container, VIEWS["rt20-labs"], `
                <input type="search" name="labQ" value="${esc(st.q)}" maxlength="200" placeholder="Search labs…">
                <label style="display:flex;align-items:center;gap:6px;font-size:13px;">
                    <input type="checkbox" name="labMine"${st.mine ? " checked" : ""}> Only my labs
                </label>
                <button type="button" class="btn btn-secondary btn-small" data-action="apply">Apply</button>
                ${canCreate ? `<button type="button" class="btn btn-small" data-action="new"><i class="fa-solid fa-plus"></i> New lab</button>` : ""}
            `);
            setStatus(container, "Loading labs…");
            return client().listLabs({
                q: st.q || undefined,
                mine: st.mine || undefined,
                limit: 100
            }).then(payload => {
                const labs = Array.isArray(payload.labs) ? payload.labs : [];
                cached(container, "labs", labs);
                setBody(container, labs.length
                    ? `<div class="rt-list">${labs.map(labItem).join("")}</div>`
                    : empty("No labs match this filter."));
                setStatus(container, `Showing ${labs.length} of ${payload.total != null ? payload.total : labs.length} labs.`);
            });
        },
        actions: {
            apply(container) {
                const st = viewState(container);
                st.q = field(container, "labQ");
                st.mine = isChecked(container, "labMine");
                closeEditor(container);
                return reload(container);
            },
            new(container) {
                openEditor(container, labForm(null));
            },
            open(container, element) {
                viewState(container).detailId = dataId(element);
                closeEditor(container);
                return reload(container);
            },
            back(container) {
                viewState(container).detailId = null;
                closeEditor(container);
                return reload(container);
            },
            edit(container) {
                const detail = cached(container, "detail");
                if (detail) openEditor(container, labForm(detail));
            },
            "member-new"(container) {
                openEditor(container, labMemberForm());
            },
            async "member-remove"(container, element) {
                const detail = cached(container, "detail");
                const userId = dataNumber(element, "user");
                if (!detail || !userId) return;
                if (!global.confirm || !global.confirm("Remove this member from the lab?")) return;
                await client().removeLabMember(detail.id, userId);
                await afterWrite(container, "Member removed.");
            },
            async delete(container) {
                const detail = cached(container, "detail");
                if (!detail) return;
                if (!global.confirm || !global.confirm("Delete this lab? Open collaborations may block deletion.")) return;
                await client().deleteLab(detail.id);
                viewState(container).detailId = null;
                await afterWrite(container, "Lab deleted.");
            },
            cancel(container) {
                closeEditor(container);
            }
        },
        forms: {
            async lab(container, form) {
                const id = field(form, "lab_id");
                const payload = {
                    name: field(form, "name"),
                    description: field(form, "description"),
                    research_areas: field(form, "research_areas"),
                    visibility: field(form, "visibility") || "institution"
                };
                if (id) {
                    await client().updateLab(Number(id), payload);
                    await afterWrite(container, "Lab saved.");
                } else {
                    const created = await client().createLab(payload);
                    viewState(container).detailId = created.id;
                    await afterWrite(container, "Lab created.");
                }
            },
            async "lab-member"(container, form) {
                const detail = cached(container, "detail");
                if (!detail) return;
                await client().addLabMember(detail.id, {
                    user_id: Number(field(form, "user_id"))
                });
                await afterWrite(container, "Member added.");
            }
        }
    });

    async function renderLabDetail(container) {
        const st = viewState(container);
        shell(container, VIEWS["rt20-labs"], `
            <button class="btn btn-secondary btn-small" type="button" data-action="back">
                <i class="fa-solid fa-arrow-left"></i> Back to labs
            </button>`);
        setStatus(container, "Loading lab…");
        const lab = await client().getLab(st.detailId);
        cached(container, "detail", lab);
        setBody(container, labDetailHTML(lab));
        setStatus(container, `${lab.member_count} member(s).`);
    }

    /* --------------------------------------------------
     * INSTITUTIONS
     * -------------------------------------------------- */

    function institutionCreateForm() {
        return `
        <form class="rt-form" data-form="institution">
            <h4 style="font-size:14px;">New institution</h4>
            <div><label>Institution name</label><input name="name" required maxlength="200"></div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Create institution</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function institutionRenameForm(institution) {
        return `
        <form class="rt-form" data-form="institution-rename">
            <h4 style="font-size:14px;">Rename institution</h4>
            <input type="hidden" name="institution_id" value="${institution.id}">
            <div><label>Institution name</label><input name="name" required maxlength="200" value="${esc(institution.name)}"></div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Save name</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function institutionMemberForm(institution, mode) {
        return `
        <form class="rt-form" data-form="institution-member" data-mode="${mode}">
            <h4 style="font-size:14px;">${mode === "assign" ? "Affiliate a member" : "Remove a member"} — ${esc(institution.name)}</h4>
            <input type="hidden" name="institution_id" value="${institution.id}">
            <div><label>User ID</label><input name="user_id" type="number" min="1" required></div>
            <p class="rt-meta">Only active student or faculty accounts can be affiliated.</p>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">${mode === "assign" ? "Affiliate member" : "Remove affiliation"}</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    defineView({
        id: "rt20-institutions",
        title: "Institutions",
        icon: "fa-building-columns",
        roles: ["student", "faculty", "admin"],
        note: "University directory. Administrators can create institutions and manage affiliations.",
        render(container) {
            const user = currentUser() || {};
            const isAdmin = user.role === "admin";
            shell(container, VIEWS["rt20-institutions"], isAdmin
                ? `<button class="btn btn-small" type="button" data-action="new"><i class="fa-solid fa-plus"></i> New institution</button>`
                : "");
            setStatus(container, "Loading institutions…");
            return Promise.all([
                client().listInstitutions(),
                client().getMyInstitution()
            ]).then(([payload, mine]) => {
                const institutions = Array.isArray(payload.institutions) ? payload.institutions : [];
                cached(container, "institutions", institutions);
                const mineHTML = mine.institution
                    ? `<div class="rt-note">Your institution: <b>${esc(mine.institution.name)}</b>
                        (${mine.institution.member_count} member(s), ${mine.institution.lab_count} lab(s))</div>`
                    : `<div class="rt-note">Your account is not affiliated with an institution yet. An administrator can affiliate you.</div>`;
                const listHTML = institutions.length
                    ? `<div class="rt-list">${institutions.map(institution => `
                        <div class="rt-item">
                            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                                <h4>${esc(institution.name)}</h4>
                                <span class="rt-meta">${institution.member_count} member(s) &middot; ${institution.lab_count} lab(s)</span>
                            </div>
                            ${isAdmin ? `<div class="rt-actions">
                                <button class="btn btn-secondary btn-small" type="button" data-action="rename" data-id="${institution.id}">Rename</button>
                                <button class="btn btn-secondary btn-small" type="button" data-action="members" data-id="${institution.id}">Members</button>
                                <button class="btn btn-secondary btn-small" type="button" data-action="assign" data-id="${institution.id}">Affiliate member</button>
                                <button class="btn btn-secondary btn-small" type="button" data-action="remove-member" data-id="${institution.id}">Remove affiliation</button>
                            </div>` : ""}
                        </div>`).join("")}</div>`
                    : empty("No institutions yet.");
                setBody(container, `${mineHTML}${listHTML}`);
                setStatus(container, `${institutions.length} institution(s) in the directory.`);
            });
        },
        actions: {
            new(container) {
                openEditor(container, institutionCreateForm());
            },
            rename(container, element) {
                const institution = findById(cached(container, "institutions") || [], dataId(element));
                if (institution) openEditor(container, institutionRenameForm(institution));
            },
            async members(container, element) {
                const institution = findById(cached(container, "institutions") || [], dataId(element));
                const id = dataId(element);
                if (!institution || !id) return;
                const payload = await client().listInstitutionMembers(id);
                const members = Array.isArray(payload.members) ? payload.members : [];
                openEditor(container, `
                    <div class="rt-detail">
                        <h4>${esc(institution.name)} members</h4>
                        ${members.length
                            ? `<div class="rt-list">${members.map(member => `
                                <div class="rt-item">
                                    <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                                        <h4>${esc(member.full_name)}</h4>
                                        <span class="rt-meta">affiliated ${fmtDate(member.created_at)}</span>
                                    </div>
                                    <div class="rt-meta">User ${member.user_id}</div>
                                </div>`).join("")}</div>`
                            : empty("No affiliated members yet.")}
                        <div class="rt-actions">
                            <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Close</button>
                        </div>
                    </div>`);
            },
            assign(container, element) {
                const institution = findById(cached(container, "institutions") || [], dataId(element));
                if (institution) openEditor(container, institutionMemberForm(institution, "assign"));
            },
            "remove-member"(container, element) {
                const institution = findById(cached(container, "institutions") || [], dataId(element));
                if (institution) openEditor(container, institutionMemberForm(institution, "remove"));
            },
            cancel(container) {
                closeEditor(container);
            }
        },
        forms: {
            async institution(container, form) {
                await client().createInstitution({ name: field(form, "name") });
                await afterWrite(container, "Institution created.");
            },
            async "institution-rename"(container, form) {
                await client().renameInstitution(Number(field(form, "institution_id")), {
                    name: field(form, "name")
                });
                await afterWrite(container, "Institution renamed.");
            },
            async "institution-member"(container, form) {
                const institutionId = Number(field(form, "institution_id"));
                const userId = Number(field(form, "user_id"));
                if (form.getAttribute("data-mode") === "remove") {
                    if (!global.confirm || !global.confirm("Remove this user's institution affiliation?")) return;
                    await client().removeInstitutionMember(institutionId, userId);
                    await afterWrite(container, "Affiliation removed.");
                } else {
                    await client().assignInstitutionMember(institutionId, userId);
                    await afterWrite(container, "Member affiliated.");
                }
            }
        }
    });

    /* --------------------------------------------------
     * INTER-UNIVERSITY COLLABORATIONS
     * -------------------------------------------------- */

    const COLLABORATION_TRANSITIONS = {
        proposed: ["active", "declined", "withdrawn"],
        active: ["completed", "withdrawn"],
        declined: [],
        completed: [],
        withdrawn: []
    };

    function collaborationForm(ownedLabs, visibleLabs) {
        if (!ownedLabs.length) {
            return `${empty("You own no lab yet. Create a lab before proposing an inter-university collaboration.")}
                <div class="rt-actions"><button class="btn btn-secondary btn-small" type="button" data-action="cancel">Close</button></div>`;
        }
        return `
        <form class="rt-form" data-form="collaboration">
            <h4 style="font-size:14px;">Propose an inter-university collaboration</h4>
            <div><label>Your lab</label><select name="requester_lab_id">${ownedLabs.map(lab =>
                `<option value="${lab.id}">${esc(lab.name)} — ${esc((lab.institution || {}).name || "No institution")}</option>`).join("")}</select></div>
            <div><label>Partner lab (another institution)</label><select name="partner_lab_id">${visibleLabs
                .filter(lab => ownedLabs.every(owned => owned.institution && lab.institution && owned.institution.id !== lab.institution.id))
                .map(lab => `<option value="${lab.id}">${esc(lab.name)} — ${esc((lab.institution || {}).name || "No institution")}</option>`).join("")}</select></div>
            <div><label>Title</label><input name="title" required maxlength="200"></div>
            <div><label>Description</label><textarea name="description" maxlength="5000"></textarea></div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Propose collaboration</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function collaborationStatusForm(collaboration, ownedLabIds) {
        const transitions = COLLABORATION_TRANSITIONS[collaboration.status] || [];
        let allowed = transitions;
        if (collaboration.status === "proposed") {
            allowed = collaboration.access_role === "partner"
                ? transitions.filter(status => status !== "withdrawn")
                : transitions.filter(status => status !== "active" && status !== "declined");
        }
        if (!allowed.length) {
            return `${empty("This collaboration is in a final state.")}
                <div class="rt-actions"><button class="btn btn-secondary btn-small" type="button" data-action="cancel">Close</button></div>`;
        }
        return `
        <form class="rt-form" data-form="collaboration-status">
            <h4 style="font-size:14px;">Update collaboration status</h4>
            <input type="hidden" name="collaboration_id" value="${collaboration.id}">
            <div class="rt-grid-2">
                <div><label>New status</label><select name="status">${options(allowed, allowed[0])}</select></div>
                <div><label>Resolution note</label><input name="note" maxlength="2000"></div>
            </div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Update status</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    defineView({
        id: "rt20-collaborations",
        title: "Inter-university Collaborations",
        icon: "fa-handshake",
        roles: ["student", "faculty"],
        note: "Collaboration proposals between labs at different institutions, with owner approval.",
        render(container) {
            const user = currentUser() || {};
            const isFaculty = user.role === "faculty";
            const st = viewState(container, { status: "" });
            shell(container, VIEWS["rt20-collaborations"], `
                <select name="collabStatus">${options([""].concat(Object.keys(COLLABORATION_TRANSITIONS)), st.status, { "": "All statuses" })}</select>
                <button type="button" class="btn btn-secondary btn-small" data-action="apply">Apply</button>
                ${isFaculty ? `<button type="button" class="btn btn-small" data-action="new"><i class="fa-solid fa-plus"></i> Propose</button>` : ""}
            `);
            setStatus(container, "Loading collaborations…");
            return Promise.all([
                client().listCollaborations({ status: st.status || undefined, limit: 100 }),
                client().listLabs({ mine: true, limit: 100 }),
                client().listLabs({ limit: 100 })
            ]).then(([payload, minePayload, allPayload]) => {
                const collaborations = Array.isArray(payload.collaborations) ? payload.collaborations : [];
                const ownedLabs = (minePayload.labs || []).filter(lab => lab.is_owner);
                const visibleLabs = Array.isArray(allPayload.labs) ? allPayload.labs : [];
                cached(container, "ownedLabs", ownedLabs);
                cached(container, "visibleLabs", visibleLabs);
                const ownedLabIds = ownedLabs.map(lab => lab.id);

                const itemHTML = collaborations.map(collaboration => {
                    const requester = collaboration.requester_lab || {};
                    const partner = collaboration.partner_lab || {};
                    const ownsRequester = ownedLabIds.indexOf(requester.id) !== -1;
                    const ownsPartner = ownedLabIds.indexOf(partner.id) !== -1;
                    const ownsRelevant = collaboration.status === "proposed"
                        ? (collaboration.access_role === "partner" ? ownsPartner : ownsRequester)
                        : (ownsRequester || ownsPartner);
                    const transitions = COLLABORATION_TRANSITIONS[collaboration.status] || [];
                    const canChange = isFaculty && ownsRelevant && transitions.length > 0;
                    return `
                    <div class="rt-item">
                        <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                            <h4>${esc(collaboration.title)} ${badge(collaboration.status)}</h4>
                            <span class="rt-meta">${esc(statusLabel(collaboration.access_role))} side</span>
                        </div>
                        ${pre(collaboration.description)}
                        <div class="rt-meta">
                            ${esc(requester.name || "Requester lab")} (${esc((requester.institution || {}).name || "—")})
                            ⇄ ${esc(partner.name || "Partner lab")} (${esc((partner.institution || {}).name || "—")})
                        </div>
                        ${collaboration.resolution_note ? pre(collaboration.resolution_note) : ""}
                        <div class="rt-actions">
                            ${canChange ? `<button class="btn btn-secondary btn-small" type="button" data-action="status-edit" data-id="${collaboration.id}">Change status</button>` : ""}
                            <span class="rt-meta">updated ${fmtDate(collaboration.updated_at)}</span>
                        </div>
                    </div>`;
                }).join("");

                cached(container, "collaborations", collaborations);
                setBody(container, collaborations.length
                    ? `<div class="rt-list">${itemHTML}</div>`
                    : empty("No collaborations yet. Faculty lab owners can propose one."));
                setStatus(container, `Showing ${collaborations.length} of ${payload.total != null ? payload.total : collaborations.length} collaborations.`);
            });
        },
        actions: {
            apply(container) {
                viewState(container).status = field(container, "collabStatus");
                closeEditor(container);
                return reload(container);
            },
            new(container) {
                openEditor(container, collaborationForm(
                    cached(container, "ownedLabs") || [],
                    cached(container, "visibleLabs") || []
                ));
            },
            "status-edit"(container, element) {
                const collaboration = findById(cached(container, "collaborations") || [], dataId(element));
                if (!collaboration) return;
                const ownedLabIds = (cached(container, "ownedLabs") || []).map(lab => lab.id);
                openEditor(container, collaborationStatusForm(collaboration, ownedLabIds));
            },
            cancel(container) {
                closeEditor(container);
            }
        },
        forms: {
            async collaboration(container, form) {
                const ownedLabs = cached(container, "ownedLabs") || [];
                const visibleLabs = cached(container, "visibleLabs") || [];
                const requesterId = Number(field(form, "requester_lab_id"));
                const partnerId = Number(field(form, "partner_lab_id"));
                const requester = findById(ownedLabs, requesterId);
                const partner = findById(visibleLabs, partnerId);
                if (!requester || !partner) throw new Error("Choose both labs.");
                if (requester.institution && partner.institution
                    && requester.institution.id === partner.institution.id) {
                    throw new Error("Choose a partner lab from another institution.");
                }
                await client().createCollaboration({
                    requester_lab_id: requesterId,
                    partner_lab_id: partnerId,
                    title: field(form, "title"),
                    description: field(form, "description")
                });
                await afterWrite(container, "Collaboration proposed.");
            },
            async "collaboration-status"(container, form) {
                await client().updateCollaborationStatus(Number(field(form, "collaboration_id")), {
                    status: field(form, "status"),
                    note: field(form, "note")
                });
                await afterWrite(container, "Collaboration status updated.");
            }
        }
    });

    /* --------------------------------------------------
     * ANALYTICS
     * -------------------------------------------------- */

    function pct(value) {
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) return "—";
        return `${Math.round(numeric * 1000) / 10}%`;
    }

    function kpi(label, value) {
        const text = value === null || value === undefined || value === "" ? "—" : value;
        return `<div class="rt-kpi"><span>${esc(label)}</span><b>${esc(text)}</b></div>`;
    }

    function analyticsHTML(summary, departments) {
        const researchers = summary.researchers || {};
        const collaboration = summary.collaboration || {};
        const areas = summary.research_areas || {};
        const accounts = summary.accounts || {};
        const topAreas = Array.isArray(areas.top) ? areas.top : [];
        const rows = Array.isArray(departments.departments) ? departments.departments : [];

        const tableRows = rows.map(row => {
            const top = (Array.isArray(row.top_research_areas) ? row.top_research_areas : [])
                .slice(0, 3)
                .map(item => `${item.area} (${item.researcher_count})`)
                .join(", ");
            const collab = row.collaboration || {};
            return `<tr>
                <td>${esc(row.department || "Unspecified")}</td>
                <td>${esc(row.researcher_count)}</td>
                <td>${row.average_experience_years == null ? "—" : esc(row.average_experience_years)}</td>
                <td>${esc(row.verified_researcher_count)} / ${esc(row.pending_verification_count)} / ${esc(row.expired_verification_count)}</td>
                <td>${esc(row.researchers_with_publications)}</td>
                <td>${esc(row.researchers_with_projects)}</td>
                <td>${esc(row.faculty_account_count)}</td>
                <td>${esc(collab.accepted || 0)} / ${esc(collab.total || 0)}</td>
                <td>${esc(top)}</td>
            </tr>`;
        }).join("");

        return `
        <div class="rt-kpis">
            ${kpi("Researchers", researchers.total)}
            ${kpi("Departments", researchers.departments)}
            ${kpi("Verified", researchers.verified)}
            ${kpi("Pending verification", researchers.pending_verification)}
            ${kpi("Expired verification", researchers.expired_verification)}
            ${kpi("With publications", researchers.with_publications)}
            ${kpi("With projects", researchers.with_projects)}
            ${kpi("Avg experience", researchers.average_experience_years == null ? "—" : `${researchers.average_experience_years} yrs`)}
        </div>
        <div class="rt-kpis">
            ${kpi("Collaboration requests", collaboration.total)}
            ${kpi("Accepted", collaboration.accepted)}
            ${kpi("Pending", collaboration.pending)}
            ${kpi("Acceptance rate", pct(collaboration.acceptance_rate))}
            ${kpi("Research areas", areas.distinct)}
            ${kpi("Students", accounts.students)}
            ${kpi("Faculty", accounts.faculty)}
            ${kpi("Admins", accounts.admins)}
        </div>
        <h4 style="font-size:14px;">Top research areas</h4>
        ${topAreas.length
            ? `<div class="rt-chips">${topAreas.map(item =>
                `<span class="rt-chip">${esc(item.area)} &middot; ${esc(item.researcher_count)}</span>`).join("")}</div>`
            : empty("No research areas recorded.")}
        <h4 style="font-size:14px;margin-top:18px;">Departments</h4>
        ${rows.length ? `
        <div class="rt-table-wrap"><table class="rt-table">
            <thead><tr>
                <th>Department</th><th>Researchers</th><th>Avg experience</th>
                <th>Verified / pending / expired</th><th>Publications</th><th>Projects</th>
                <th>Faculty accounts</th><th>Collaborations</th><th>Top areas</th>
            </tr></thead>
            <tbody>${tableRows}</tbody>
        </table></div>` : empty("No departments match this filter.")}`;
    }

    defineView({
        id: "rt20-analytics",
        title: "Analytics",
        icon: "fa-chart-column",
        roles: ["student", "faculty", "admin"],
        note: "University and department research analytics derived from stored records.",
        render(container) {
            const st = viewState(container, { department: "" });
            shell(container, VIEWS["rt20-analytics"], `
                <input type="search" name="analyticsDepartment" value="${esc(st.department)}" maxlength="150" placeholder="Exact department name…">
                <button type="button" class="btn btn-secondary btn-small" data-action="apply">Apply</button>
                <button type="button" class="btn btn-secondary btn-small" data-action="clear">Clear</button>
            `);
            setStatus(container, "Loading analytics…");
            return Promise.all([
                client().getUniversityAnalytics(),
                client().getDepartmentAnalytics({
                    department: st.department || undefined,
                    limit: 100
                })
            ]).then(([summary, departments]) => {
                cached(container, "summary", summary);
                setBody(container, analyticsHTML(summary, departments));
                setStatus(container, `Showing ${departments.departments.length} of ${departments.total} departments.`);
            });
        },
        actions: {
            apply(container) {
                viewState(container).department = field(container, "analyticsDepartment");
                return reload(container);
            },
            clear(container) {
                viewState(container).department = "";
                return reload(container);
            }
        }
    });

    /* --------------------------------------------------
     * RESEARCH INTELLIGENCE
     * -------------------------------------------------- */

    const INTELLIGENCE_SECTIONS = [
        ["network", "Network"],
        ["clusters", "Clusters"],
        ["trends", "Trends"],
        ["topics", "Topic prediction"],
        ["graph", "Knowledge graph"]
    ];

    function intelligenceTabs(st) {
        return INTELLIGENCE_SECTIONS.map(([id, label]) =>
            `<button type="button" class="btn ${st.section === id ? "btn-small" : "btn-secondary btn-small"}" data-action="section" data-section="${id}">${esc(label)}</button>`
        ).join("");
    }

    async function renderNetworkSection(container, st) {
        shell(container, VIEWS["rt20-intelligence"], `
            ${intelligenceTabs(st)}
            <label style="font-size:12px;">Min similarity
                <input type="number" name="networkMin" min="0" max="1" step="0.01" value="${esc(st.minSimilarity)}" style="width:80px;">
            </label>
            <input type="search" name="networkDepartment" value="${esc(st.department)}" maxlength="150" placeholder="Department (exact)…">
            <label style="display:flex;align-items:center;gap:6px;font-size:13px;">
                <input type="checkbox" name="networkIsolated"${st.includeIsolated ? " checked" : ""}> Include isolated
            </label>
            <button type="button" class="btn btn-secondary btn-small" data-action="apply-network">Apply</button>
        `);
        setStatus(container, "Computing the research network…");
        const minSimilarity = Number(st.minSimilarity);
        if (!Number.isFinite(minSimilarity) || minSimilarity < 0 || minSimilarity > 1) {
            throw new Error("Minimum similarity must be between 0 and 1.");
        }
        const payload = await client().getResearchNetwork({
            min_similarity: minSimilarity,
            max_edges: 300,
            department: st.department || undefined,
            include_isolated: st.includeIsolated
        });
        const nodes = Array.isArray(payload.nodes) ? payload.nodes : [];
        const edges = Array.isArray(payload.edges) ? payload.edges : [];
        const names = {};
        nodes.forEach(node => { names[node.id] = node.name; });

        const nodeRows = nodes.slice()
            .sort((left, right) => (right.degree || 0) - (left.degree || 0))
            .slice(0, 100)
            .map(node => `<tr>
                <td>${esc(node.name)}</td>
                <td>${esc(node.department || "—")}</td>
                <td>${esc(node.degree)}</td>
                <td>${esc(node.cluster_label || "—")}</td>
                <td>${esc((node.research_areas || []).join(", "))}</td>
            </tr>`).join("");
        const edgeRows = edges.slice(0, 100).map(edge => `<tr>
                <td>${esc(names[edge.source] || edge.source)}</td>
                <td>${esc(names[edge.target] || edge.target)}</td>
                <td>${esc(Number(edge.similarity).toFixed(3))}</td>
            </tr>`).join("");

        setBody(container, `
            <p class="rt-meta">Method ${esc(payload.method)} &middot; minimum similarity ${esc(payload.min_similarity)}.</p>
            <h4 style="font-size:14px;">Most connected researchers</h4>
            ${nodes.length ? `<div class="rt-table-wrap"><table class="rt-table">
                <thead><tr><th>Researcher</th><th>Department</th><th>Degree</th><th>Cluster</th><th>Research areas</th></tr></thead>
                <tbody>${nodeRows}</tbody>
            </table></div>` : empty("No researchers match this filter.")}
            <h4 style="font-size:14px;margin-top:18px;">Strongest similarity edges</h4>
            ${edges.length ? `<div class="rt-table-wrap"><table class="rt-table">
                <thead><tr><th>Researcher</th><th>Researcher</th><th>Similarity</th></tr></thead>
                <tbody>${edgeRows}</tbody>
            </table></div>
            ${edges.length > 100 ? `<p class="rt-meta">Showing the 100 strongest of ${esc(edges.length)} returned edges.</p>` : ""}`
            : empty("No similarity edges meet this threshold.")}`);
        setStatus(
            container,
            `${payload.node_count} researcher(s), ${payload.edge_count} similarity edge(s).${payload.truncated ? " The server truncated the edge list." : ""}`
        );
    }

    function intelligenceRebuildForm() {
        return `
        <form class="rt-form" data-form="intelligence-rebuild">
            <h4 style="font-size:14px;">Rebuild research clusters</h4>
            <div class="rt-grid-2">
                <div><label>Minimum similarity (0.05–0.95)</label>
                    <input name="min_similarity" type="number" min="0.05" max="0.95" step="0.01" value="0.18"></div>
                <div><label>Semantic blending</label>
                    <label style="display:flex;align-items:center;gap:6px;font-size:13px;">
                        <input type="checkbox" name="use_semantic" checked> Use embeddings when available
                    </label></div>
            </div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Rebuild clusters</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    async function renderClusterSection(container, st) {
        const user = currentUser() || {};
        shell(container, VIEWS["rt20-intelligence"], `
            ${intelligenceTabs(st)}
            ${user.role === "admin"
                ? `<button type="button" class="btn btn-small" data-action="rebuild"><i class="fa-solid fa-arrows-rotate"></i> Rebuild clusters</button>`
                : ""}
        `);
        setStatus(container, "Loading cluster state…");
        const payload = await client().getResearchClusters();
        const clusters = Array.isArray(payload.clusters) ? payload.clusters : [];
        const run = payload.run;
        setBody(container, !run
            ? empty(user.role === "admin"
                ? "No clustering run has been recorded yet. Use Rebuild clusters to create one."
                : "No clustering run has been recorded yet. An administrator can rebuild clusters.")
            : `
            <p class="rt-meta">Run #${esc(run.id)} &middot; ${esc(run.method)}
                &middot; semantic ${run.semantic_used ? "on" : "off"}
                &middot; ${esc(run.researcher_count)} researcher(s) in ${esc(run.cluster_count)} cluster(s)
                &middot; ${fmtDate(run.created_at)}</p>
            <div class="rt-list">${clusters.map(cluster => `
                <div class="rt-item">
                    <h4>${esc(cluster.label || `Cluster ${cluster.cluster_index + 1}`)}
                        <span class="rt-meta">${esc(cluster.researcher_count)} member(s)</span></h4>
                    ${chips((cluster.members || []).map(member => member.name))}
                </div>`).join("")}</div>`);
        setStatus(container, run
            ? `${clusters.length} cluster(s) in the latest run.`
            : "No clustering run recorded.");
    }

    async function renderTrendSection(container, st) {
        shell(container, VIEWS["rt20-intelligence"], intelligenceTabs(st));
        setStatus(container, "Loading topic trends…");
        const payload = await client().getResearchTrends({ top_k: 10 });
        const source = payload.generated_from || {};
        const topics = Array.isArray(payload.topics) ? payload.topics : [];
        const co = Array.isArray(payload.co_occurring_topics) ? payload.co_occurring_topics : [];
        const temporal = payload.temporal || {};

        setBody(container, `
            <p class="rt-meta">Based on ${esc(source.researcher_count)} researcher(s),
                ${esc(source.researchers_with_research_areas)} with research areas and
                ${esc(source.researchers_with_publications)} with publications.</p>
            ${topics.length ? `<div class="rt-table-wrap"><table class="rt-table">
                <thead><tr><th>Topic</th><th>Researchers</th><th>Share</th><th>Top departments</th></tr></thead>
                <tbody>${topics.map(topic => `<tr>
                    <td>${esc(topic.topic)}</td>
                    <td>${esc(topic.researcher_count)}</td>
                    <td>${pct(topic.share)}</td>
                    <td>${esc((topic.departments || []).slice(0, 3)
                        .map(entry => `${entry.department} (${entry.researcher_count})`)
                        .join(", "))}</td>
                </tr>`).join("")}</tbody>
            </table></div>` : empty("No topics are available yet.")}
            <h4 style="font-size:14px;margin-top:18px;">Co-occurring topics</h4>
            ${co.length
                ? chips(co.map(item => `${item.topics.join(" + ")} (${item.researcher_count})`))
                : empty("No co-occurring topics recorded.")}
            ${temporal.available ? "" : `<p class="rt-note">${esc(temporal.reason || "No dated trend series is available.")}</p>`}`);
        setStatus(container, `${topics.length} topic(s) in the current snapshot.`);
    }

    function topicForm() {
        return `
        <form class="rt-form" data-form="intelligence-topics">
            <h4 style="font-size:14px;">Predict research topics</h4>
            <div><label>Research description</label>
                <textarea name="text" required maxlength="5000" placeholder="Paste an abstract, proposal summary or research interests…"></textarea></div>
            <div><label>Number of topics</label>
                <select name="top_k">${options(["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"], "5")}</select></div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Predict topics</button>
            </div>
        </form>`;
    }

    function topicsHTML(payload) {
        const topics = Array.isArray(payload.topics) ? payload.topics : [];
        if (!topics.length) return empty("No topics were predicted from this text.");
        return `
        <p class="rt-meta">${esc(payload.method)} &middot; matched ${esc(payload.matched_researcher_count)}
            of ${esc(payload.labeled_researcher_count)} labelled researcher(s).</p>
        <div class="rt-list">${topics.map(topic => `
            <div class="rt-item">
                <h4>${esc(topic.topic)}
                    <span class="rt-meta">score ${esc(topic.score)} &middot; ${esc(topic.researcher_count)} researcher(s)</span></h4>
                ${chips((topic.evidence || []).map(item =>
                    `${item.name} (${item.department || "no department"})`))}
            </div>`).join("")}</div>`;
    }

    function renderTopicSection(container, st) {
        shell(container, VIEWS["rt20-intelligence"], intelligenceTabs(st));
        const previous = cached(container, "topics");
        setBody(container, topicForm() + (previous ? topicsHTML(previous) : ""));
        setStatus(container, previous
            ? `Predicted ${(previous.topics || []).length} topic(s).`
            : "Describe a research area to see propagated topics.");
    }

    async function renderGraphSection(container, st) {
        shell(container, VIEWS["rt20-intelligence"], `
            ${intelligenceTabs(st)}
            <label style="display:flex;align-items:center;gap:6px;font-size:13px;">
                <input type="checkbox" name="graphVerified"${st.verifiedOnly ? " checked" : ""}> Verified researchers only
            </label>
            <label style="font-size:12px;">Researcher limit
                <input type="number" name="graphLimit" min="1" max="500" step="1" value="${esc(st.researcherLimit)}" style="width:80px;">
            </label>
            <button type="button" class="btn btn-secondary btn-small" data-action="apply-graph">Apply</button>
        `);
        setStatus(container, "Building the knowledge graph…");
        const limit = Number(st.researcherLimit);
        if (!Number.isInteger(limit) || limit < 1 || limit > 500) {
            throw new Error("Researcher limit must be between 1 and 500.");
        }
        const payload = await client().getKnowledgeGraph({
            verified_only: st.verifiedOnly,
            researcher_limit: limit
        });
        const meta = payload.meta || {};
        const nodes = Array.isArray(payload.nodes) ? payload.nodes : [];
        const byType = {};
        const counts = {};
        nodes.forEach(node => {
            const type = node.type || "entity";
            counts[type] = (counts[type] || 0) + 1;
            if (!byType[type]) byType[type] = [];
            if (byType[type].length < 50) byType[type].push(node);
        });
        const sections = Object.keys(counts).sort().map(type => `
            <h4 style="font-size:13px;margin-top:14px;">${esc(statusLabel(type))} (${esc(counts[type])})</h4>
            ${chips(byType[type].map(node => node.label))}
        `).join("");

        setBody(container, `
            <div class="rt-kpis">
                ${kpi("Researchers", meta.researcher_count)}
                ${kpi("Nodes", meta.node_count)}
                ${kpi("Edges", meta.edge_count)}
            </div>
            <p class="rt-meta">${Object.entries(meta.verification_status_counts || {})
                .map(([key, value]) => `${statusLabel(key)}: ${value}`)
                .map(esc)
                .join(" · ")}</p>
            ${sections || empty("No graph nodes were returned.")}`);
        setStatus(container, `${meta.node_count} node(s) and ${meta.edge_count} relation(s).`);
    }

    defineView({
        id: "rt20-intelligence",
        title: "Research Intelligence",
        icon: "fa-diagram-project",
        roles: ["student", "faculty", "admin"],
        note: "Researcher similarity network, topic clusters, topic prediction, trends and the knowledge graph.",
        render(container) {
            const st = viewState(container, {
                section: "network",
                minSimilarity: "0.1",
                department: "",
                includeIsolated: true,
                verifiedOnly: false,
                researcherLimit: "200"
            });
            if (st.section === "network") return renderNetworkSection(container, st);
            if (st.section === "clusters") return renderClusterSection(container, st);
            if (st.section === "trends") return renderTrendSection(container, st);
            if (st.section === "topics") return renderTopicSection(container, st);
            return renderGraphSection(container, st);
        },
        actions: {
            section(container, element) {
                viewState(container).section = element.getAttribute("data-section") || "network";
                cached(container, "topics", null);
                closeEditor(container);
                return reload(container);
            },
            "apply-network"(container) {
                const st = viewState(container);
                st.minSimilarity = field(container, "networkMin") || "0.1";
                st.department = field(container, "networkDepartment");
                st.includeIsolated = isChecked(container, "networkIsolated");
                return reload(container);
            },
            "apply-graph"(container) {
                const st = viewState(container);
                st.verifiedOnly = isChecked(container, "graphVerified");
                st.researcherLimit = field(container, "graphLimit") || "200";
                return reload(container);
            },
            rebuild(container) {
                openEditor(container, intelligenceRebuildForm());
            },
            cancel(container) {
                closeEditor(container);
            }
        },
        forms: {
            async "intelligence-topics"(container, form) {
                const text = field(form, "text");
                if (!text) throw new Error("Provide text to classify.");
                setStatus(container, "Predicting topics…");
                const payload = await client().predictTopics({
                    text,
                    top_k: Number(field(form, "top_k"))
                });
                cached(container, "topics", payload);
                setBody(container, topicForm() + topicsHTML(payload));
                setStatus(container, `Predicted ${(payload.topics || []).length} topic(s).`, "success");
            },
            async "intelligence-rebuild"(container, form) {
                const min = Number(field(form, "min_similarity"));
                if (!Number.isFinite(min) || min < 0.05 || min > 0.95) {
                    throw new Error("Minimum similarity must be between 0.05 and 0.95.");
                }
                await client().rebuildResearchClusters({
                    min_similarity: min,
                    use_semantic: isChecked(form, "use_semantic")
                });
                await afterWrite(container, "Clusters rebuilt.");
            }
        }
    });

    /* --------------------------------------------------
     * RESEARCHER VERIFICATION
     * -------------------------------------------------- */

    const ADMIN_VERIFICATION_FILTERS = ["all", "pending", "verified", "rejected", "expired"];

    function verificationDatesHTML(record) {
        return `<div class="rt-meta">
            Submitted ${fmtDate(record.submitted_at)}
            &middot; Reviewed ${fmtDate(record.reviewed_at)}
            &middot; Verified ${fmtDate(record.verified_at)}
            &middot; Expires ${fmtDate(record.expires_at)}
        </div>`;
    }

    function verificationSubmitForm() {
        return `
        <form class="rt-form" data-form="verification-submit">
            <h4 style="font-size:14px;">Submit verification evidence</h4>
            <div><label>Evidence reference</label>
                <input name="evidence_reference" required minlength="3" maxlength="2000" placeholder="ORCID, institutional profile URL or publication record"></div>
            <div><label>Note</label>
                <textarea name="note" maxlength="2000" placeholder="Optional context for the reviewer"></textarea></div>
            <p class="rt-meta">Submissions are rate limited to 5 per hour and one request may be pending per researcher record.</p>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Submit for review</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function verificationDecisionForm(record) {
        return `
        <form class="rt-form" data-form="verification-decision">
            <h4 style="font-size:14px;">Review request #${esc(record.id)} — ${esc(record.researcher_name || `Researcher #${record.researcher_id}`)}</h4>
            <input type="hidden" name="verification_id" value="${esc(record.id)}">
            <div><label>Decision</label>
                <select name="decision">${options(["verify", "reject"], "verify")}</select></div>
            <div><label>Review note</label><textarea name="review_note" maxlength="2000"></textarea></div>
            <div><label>Expires in days (optional, 1–3650)</label>
                <input name="expires_in_days" type="number" min="1" max="3650"></div>
            <div class="rt-actions">
                <button class="btn btn-small" type="submit">Record decision</button>
                <button class="btn btn-secondary btn-small" type="button" data-action="cancel">Cancel</button>
            </div>
        </form>`;
    }

    function adminVerificationItem(record) {
        return `
        <div class="rt-item">
            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                <h4>${esc(record.researcher_name || `Researcher #${record.researcher_id}`)} ${badge(record.status)}</h4>
                <span class="rt-meta">#${esc(record.id)}</span>
            </div>
            ${verificationDatesHTML(record)}
            ${record.evidence_reference ? `<p><strong>Evidence:</strong> ${esc(record.evidence_reference)}</p>` : ""}
            ${record.note ? `<p><strong>Submitter note:</strong> ${esc(record.note)}</p>` : ""}
            <p class="rt-meta">Submitted by ${esc(record.submitted_by_email || `user #${record.submitted_by_user_id || "unknown"}`)}${record.reviewed_by_email ? ` &middot; reviewed by ${esc(record.reviewed_by_email)}` : ""}</p>
            ${record.review_note ? `<p><strong>Review note:</strong> ${esc(record.review_note)}</p>` : ""}
            ${record.status === "pending"
                ? `<div class="rt-actions">
                    <button type="button" class="btn btn-secondary btn-small" data-action="review" data-id="${esc(record.id)}">Review</button>
                </div>`
                : ""}
        </div>`;
    }

    async function renderFacultyVerification(container) {
        shell(container, VIEWS["rt20-verification"], "");
        setStatus(container, "Loading verification status…");
        let record;
        try {
            record = await client().getMyVerification();
        } catch (error) {
            if (error && error.status === 400) {
                setBody(container, `<p class="rt-note">Your faculty account is not linked to a researcher profile. Link it from the Faculty Profile area before submitting verification.</p>`);
                setStatus(container, "");
                return;
            }
            throw error;
        }
        cached(container, "verification", record);
        const canSubmit = record.status !== "pending";
        setBody(container, `
            <div class="rt-item">
                <h4>Researcher #${esc(record.researcher_id)} ${badge(record.status)}</h4>
                ${verificationDatesHTML(record)}
                ${record.evidence_reference ? `<p><strong>Evidence:</strong> ${esc(record.evidence_reference)}</p>` : ""}
                ${record.note ? `<p><strong>Your note:</strong> ${esc(record.note)}</p>` : ""}
                ${record.review_note ? `<p><strong>Reviewer note:</strong> ${esc(record.review_note)}</p>` : ""}
            </div>
            ${canSubmit
                ? `<div class="rt-actions">
                    <button type="button" class="btn btn-small" data-action="submit">Submit verification request</button>
                </div>`
                : `<p class="rt-note">A verification request is pending review.</p>`}`);
        setStatus(container, `Current status: ${statusLabel(record.status)}.`);
    }

    async function renderAdminVerification(container) {
        const st = viewState(container, { status: "pending" });
        shell(container, VIEWS["rt20-verification"], `
            <select name="verificationStatus">
                ${options(ADMIN_VERIFICATION_FILTERS, st.status, { all: "All requests" })}
            </select>
            <button type="button" class="btn btn-secondary btn-small" data-action="apply">Apply</button>
        `);
        setStatus(container, "Loading verification requests…");
        const payload = await client().listAdminVerifications({
            status: st.status === "all" ? undefined : st.status,
            limit: 200
        });
        const records = Array.isArray(payload.verifications) ? payload.verifications : [];
        cached(container, "records", records);
        setBody(container, records.length
            ? `<div class="rt-list">${records.map(adminVerificationItem).join("")}</div>`
            : empty("No verification requests match this filter."));
        setStatus(container, `Showing ${records.length} of ${payload.total} request(s).`);
    }

    defineView({
        id: "rt20-verification",
        title: "Researcher Verification",
        icon: "fa-shield-halved",
        roles: ["faculty", "admin"],
        note: "Faculty submit evidence for their linked researcher record; administrators review pending requests.",
        render(container) {
            const user = currentUser() || {};
            return user.role === "admin"
                ? renderAdminVerification(container)
                : renderFacultyVerification(container);
        },
        actions: {
            apply(container) {
                viewState(container).status = field(container, "verificationStatus") || "pending";
                closeEditor(container);
                return reload(container);
            },
            submit(container) {
                openEditor(container, verificationSubmitForm());
            },
            review(container, element) {
                const id = dataId(element);
                const records = cached(container, "records") || [];
                const record = records.find(item => item.id === id);
                if (record) openEditor(container, verificationDecisionForm(record));
            },
            cancel(container) {
                closeEditor(container);
            }
        },
        forms: {
            async "verification-submit"(container, form) {
                await client().submitMyVerification({
                    evidence_reference: field(form, "evidence_reference"),
                    note: field(form, "note")
                });
                await afterWrite(container, "Verification request submitted.");
            },
            async "verification-decision"(container, form) {
                const decision = field(form, "decision");
                const expiresRaw = field(form, "expires_in_days");
                const expires = expiresRaw ? Number(expiresRaw) : null;
                if (expires !== null && (!Number.isInteger(expires) || expires < 1 || expires > 3650)) {
                    throw new Error("Expiry must be between 1 and 3650 days or left blank.");
                }
                await client().decideVerification(Number(field(form, "verification_id")), {
                    decision,
                    review_note: field(form, "review_note"),
                    expires_in_days: decision === "verify" ? expires : null
                });
                await afterWrite(container, "Decision recorded.");
            }
        }
    });

    /* --------------------------------------------------
     * SEARCH HISTORY
     * -------------------------------------------------- */

    function replayDirectorySearch(query) {
        const text = String(query || "").trim();
        if (!text) return;
        const input = document.getElementById("facSearch");
        if (input) input.value = text;
        if (typeof global.switchView !== "function") return;
        global.switchView("directoryView");
        if (!document.getElementById("facSearch") && typeof global.loadDirectory === "function") {
            global.loadDirectory();
        }
    }

    function searchHistoryItem(entry) {
        return `
        <div class="rt-item">
            <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;">
                <h4>${esc(entry.query)}</h4>
                <span class="rt-meta">${fmtDate(entry.created_at)}</span>
            </div>
            <div class="rt-actions">
                <button type="button" class="btn btn-secondary btn-small" data-action="replay" data-query="${esc(entry.query)}">Replay in directory</button>
            </div>
        </div>`;
    }

    defineView({
        id: "rt20-search-history",
        title: "Search History",
        icon: "fa-clock-rotate-left",
        roles: ["student", "faculty", "admin"],
        note: "Your recent researcher-directory searches, stored per account (up to 20 entries).",
        render(container) {
            shell(container, VIEWS["rt20-search-history"], `
                <input type="search" name="historyQuery" maxlength="200" placeholder="Search the researcher directory…">
                <button type="button" class="btn btn-small" data-action="search">
                    <i class="fa-solid fa-magnifying-glass"></i> Search
                </button>
            `);
            setStatus(container, "Loading search history…");
            return client().getSearchHistory(50).then(entries => {
                const list = Array.isArray(entries) ? entries : [];
                setBody(container, list.length
                    ? `<div class="rt-list">${list.map(searchHistoryItem).join("")}</div>`
                    : empty("No searches recorded yet. Searches you make in the researcher directory appear here."));
                setStatus(container, `${list.length} recent search(es).`);
            });
        },
        actions: {
            async search(container) {
                const query = field(container, "historyQuery");
                if (query.length < 2) throw new Error("Enter at least two characters to search.");
                await client().recordSearch(query);
                replayDirectorySearch(query);
            },
            replay(container, element) {
                replayDirectorySearch(element.getAttribute("data-query") || "");
            }
        }
    });

    global.RT20 = {
        navItems,
        switchView,
        reset
    };
})(typeof window !== "undefined" ? window : this);
