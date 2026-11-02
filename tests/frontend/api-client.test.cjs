const test = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");

const { createApi, ApiError } = require("../../frontend/api-client.js");
const apiClientSource = readFileSync(require.resolve("../../frontend/api-client.js"), "utf8");

function loadBrowserApi(window) {
  vm.runInNewContext(apiClientSource, { window, URL, AbortController, setTimeout, clearTimeout });
  return window.ResearchTwinAPI;
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
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
    keys() {
      return [...map.keys()];
    },
  };
}

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function makeApi(fetchImpl, overrides = {}) {
  const storage = overrides.storage || memoryStorage();
  let unauthorizedCalls = 0;
  const api = createApi({
    baseUrl: "https://api.example.test/",
    storage,
    fetchImpl,
    onUnauthorized() {
      unauthorizedCalls += 1;
    },
    ...overrides,
  });
  return { api, storage, unauthorized: () => unauthorizedCalls };
}

test("login stores the token and does not send an Authorization header", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return jsonResponse(200, {
      access_token: "token-123",
      token_type: "bearer",
      expires_at: 999,
      user: { id: 1, email: "student@example.edu", role: "student" },
    });
  };
  const { api, storage } = makeApi(fetchImpl);

  const body = await api.login({
    email: "student@example.edu",
    password: "CorrectHorseBattery9",
  });

  assert.equal(body.user.role, "student");
  assert.equal(storage.getItem("researchtwin.sessionToken"), "token-123");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://api.example.test/auth/login");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.headers.Authorization, undefined);
  assert.equal(
    JSON.parse(calls[0].options.body).password,
    "CorrectHorseBattery9"
  );
});

test("protected requests attach the bearer token", async () => {
  let seen;
  const fetchImpl = async (url, options) => {
    seen = options;
    return jsonResponse(200, { id: 1, email: "student@example.edu" });
  };
  const { api, storage } = makeApi(fetchImpl, {
    storage: memoryStorage({ "researchtwin.sessionToken": "token-123" }),
  });

  await api.me();

  assert.equal(seen.headers.Authorization, "Bearer token-123");
  assert.equal(storage.getItem("researchtwin.sessionToken"), "token-123");
});

test("401 clears the session, notifies once, and does not retry", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return jsonResponse(401, { detail: "Authentication required" });
  };
  const { api, storage, unauthorized } = makeApi(fetchImpl, {
    storage: memoryStorage({ "researchtwin.sessionToken": "expired" }),
  });

  await assert.rejects(api.getStudentProfile(), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 401);
    assert.equal(error.kind, "unauthorized");
    assert.equal(error.message, "Authentication required");
    return true;
  });

  assert.equal(storage.getItem("researchtwin.sessionToken"), null);
  assert.equal(calls.length, 1);
  assert.equal(unauthorized(), 1);
});

test("403 keeps the session and reports a forbidden error", async () => {
  const fetchImpl = async () =>
    jsonResponse(403, {
      detail: "You do not have permission to perform this action",
    });
  const { api, storage, unauthorized } = makeApi(fetchImpl, {
    storage: memoryStorage({ "researchtwin.sessionToken": "valid" }),
  });

  await assert.rejects(api.getFacultyProfile(), (error) => {
    assert.equal(error.status, 403);
    assert.equal(error.kind, "forbidden");
    return true;
  });

  assert.equal(storage.getItem("researchtwin.sessionToken"), "valid");
  assert.equal(unauthorized(), 0);
});

test("non-JSON error bodies are handled without throwing a parse error", async () => {
  const fetchImpl = async () =>
    new Response("Internal Server Error", { status: 500 });
  const { api } = makeApi(fetchImpl);

  await assert.rejects(api.getStudentProfile(), (error) => {
    assert.equal(error.status, 500);
    assert.equal(error.kind, "http");
    assert.match(error.message, /Internal Server Error/);
    return true;
  });
});

test("timeouts abort the request and report a timeout error", async () => {
  const fetchImpl = (url, options) =>
    new Promise((resolve, reject) => {
      options.signal.addEventListener("abort", () => {
        const error = new Error("Aborted");
        error.name = "AbortError";
        reject(error);
      });
    });
  const { api } = makeApi(fetchImpl, { timeoutMs: 5 });

  await assert.rejects(api.getResearchers(), (error) => {
    assert.equal(error.kind, "timeout");
    assert.match(error.message, /timed out/i);
    return true;
  });
});

test("researcher directory remains public while authenticated APIs keep using bearer auth", async () => {
  let seen;
  const fetchImpl = async (url, options) => {
    seen = { url, options };
    return jsonResponse(200, []);
  };
  const { api } = makeApi(fetchImpl, {
    storage: memoryStorage({ "researchtwin.sessionToken": "token-123" }),
  });

  await api.getResearchers();

  assert.equal(seen.url, "https://api.example.test/researchers/");
  assert.equal(seen.options.method, "GET");
  assert.equal(seen.options.headers.Authorization, undefined);
});

test("profile saves use PUT with a JSON body", async () => {
  let seen;
  const fetchImpl = async (url, options) => {
    seen = { url, options };
    return jsonResponse(200, { skills: "Python", profile_completion: 14 });
  };
  const { api } = makeApi(fetchImpl, {
    storage: memoryStorage({ "researchtwin.sessionToken": "token-123" }),
  });

  await api.saveStudentProfile({ skills: "Python" });

  assert.equal(seen.url, "https://api.example.test/students/me/profile");
  assert.equal(seen.options.method, "PUT");
  assert.equal(seen.options.headers["Content-Type"], "application/json");
  assert.equal(JSON.parse(seen.options.body).skills, "Python");
});

test("recommendations call the authenticated endpoint with top_k", async () => {
  let seen;
  const fetchImpl = async (url, options) => {
    seen = { url, options };
    return jsonResponse(200, { recommendations: [] });
  };
  const { api } = makeApi(fetchImpl, {
    storage: memoryStorage({ "researchtwin.sessionToken": "token-123" }),
  });

  await api.getRecommendations(3);

  assert.equal(
    seen.url,
    "https://api.example.test/students/me/recommendations"
  );
  assert.equal(seen.options.method, "POST");
  assert.deepEqual(JSON.parse(seen.options.body), { top_k: 3 });
  assert.equal(seen.options.headers.Authorization, "Bearer token-123");
});

test("logout revokes on the server and clears the token even on failure", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return jsonResponse(503, { detail: "Database unavailable" });
  };
  const { api, storage } = makeApi(fetchImpl, {
    storage: memoryStorage({ "researchtwin.sessionToken": "token-123" }),
  });

  await assert.rejects(api.logout());

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://api.example.test/auth/logout");
  assert.equal(storage.getItem("researchtwin.sessionToken"), null);
});

test("only the token is stored; passwords never reach storage", async () => {
  const storage = memoryStorage();
  const fetchImpl = async () =>
    jsonResponse(200, {
      access_token: "token-abc",
      token_type: "bearer",
      expires_at: 1,
      user: { id: 1, role: "student" },
    });
  const { api } = makeApi(fetchImpl, { storage });

  await api.login({
    email: "student@example.edu",
    password: "CorrectHorseBattery9",
  });

  assert.deepEqual(storage.keys(), ["researchtwin.sessionToken"]);
  assert.equal(storage.getItem("researchtwin.sessionToken"), "token-abc");
});

test("registration uses the backend schema and stores the returned token", async () => {
  let seen;
  const fetchImpl = async (url, options) => {
    seen = { url, options };
    return jsonResponse(201, {
      access_token: "token-new",
      token_type: "bearer",
      expires_at: 1,
      user: { id: 7, role: "faculty" },
    });
  };
  const { api, storage } = makeApi(fetchImpl);

  await api.register({
    email: "faculty@example.edu",
    password: "CorrectHorseBattery9",
    full_name: "Faculty Member",
    role: "faculty",
  });

  const payload = JSON.parse(seen.options.body);
  assert.equal(seen.options.method, "POST");
  assert.equal(seen.options.headers.Authorization, undefined);
  assert.deepEqual(Object.keys(payload).sort(), [
    "email",
    "full_name",
    "password",
    "role",
  ]);
  assert.equal(storage.getItem("researchtwin.sessionToken"), "token-new");
});

test("FastAPI validation detail arrays are flattened safely", async () => {
  const fetchImpl = async () =>
    jsonResponse(422, {
      detail: [
        {
          loc: ["body", "password"],
          msg: "String should have at least 8 characters",
        },
      ],
    });
  const { api } = makeApi(fetchImpl);

  await assert.rejects(
    api.register({
      email: "bad@example.edu",
      password: "short",
      full_name: "Bad",
      role: "student",
    }),
    (error) => {
      assert.equal(error.status, 422);
      assert.match(error.message, /at least 8 characters/);
      return true;
    }
  );
});

test("roadmap calls the student-scoped GET route", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return jsonResponse(200, { researcher: { id: 7 }, skill_gaps: [], progress: {} });
  };
  const { api } = makeApi(fetchImpl, { storage: memoryStorage({ "researchtwin.sessionToken": "tok" }) });

  const body = await api.getRoadmap(7);

  assert.equal(body.skill_gaps.length, 0);
  assert.equal(calls[0].url, "https://api.example.test/students/me/researchers/7/roadmap");
  assert.equal(calls[0].options.method, "GET");
  assert.equal(calls[0].options.headers.Authorization, "Bearer tok");
});

test("milestone update sends the server-authoritative payload", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return jsonResponse(200, { progress: { completion_percentage: 17 } });
  };
  const { api } = makeApi(fetchImpl, { storage: memoryStorage({ "researchtwin.sessionToken": "tok" }) });

  const body = await api.setRoadmapMilestone(7, "pytorch", 0, true);

  assert.equal(body.progress.completion_percentage, 17);
  assert.equal(
    calls[0].url,
    "https://api.example.test/students/me/researchers/7/roadmap/progress"
  );
  assert.equal(calls[0].options.method, "PUT");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    skill: "pytorch",
    milestone_index: 0,
    completed: true,
  });
});

test("collaboration request is sent with the bearer token", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return jsonResponse(201, { id: 1, status: "pending" });
  };
  const { api } = makeApi(fetchImpl, { storage: memoryStorage({ "researchtwin.sessionToken": "tok" }) });

  const body = await api.createCollaborationRequest(3, "I would like to collaborate.");

  assert.equal(body.status, "pending");
  assert.equal(calls[0].url, "https://api.example.test/students/me/collaboration-requests");
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    researcher_id: 3,
    message: "I would like to collaborate.",
  });
});

test("duplicate collaboration request surfaces the server detail", async () => {
  const fetchImpl = async () =>
    jsonResponse(409, { detail: "You already have a pending request with this researcher" });
  const { api } = makeApi(fetchImpl);

  await assert.rejects(api.createCollaborationRequest(3, "Again"), (error) => {
    assert.equal(error.status, 409);
    assert.equal(error.kind, "http");
    assert.match(error.message, /already have a pending request/);
    return true;
  });
});

test("faculty decision keeps the session on 403 and reports forbidden", async () => {
  const storage = memoryStorage({ "researchtwin.sessionToken": "tok" });
  const fetchImpl = async () =>
    jsonResponse(403, { detail: "You can only respond to requests addressed to your linked record" });
  const { api, unauthorized } = makeApi(fetchImpl, { storage });

  await assert.rejects(api.decideCollaborationRequest(9, "accept", ""), (error) => {
    assert.equal(error.kind, "forbidden");
    return true;
  });

  assert.equal(storage.getItem("researchtwin.sessionToken"), "tok");
  assert.equal(unauthorized(), 0);
});

test("faculty inbox passes the status filter through", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return jsonResponse(200, { researcher: null, requests: [] });
  };
  const { api } = makeApi(fetchImpl, { storage: memoryStorage({ "researchtwin.sessionToken": "tok" }) });

  await api.listFacultyCollaborationRequests("pending");

  assert.equal(
    calls[0].url,
    "https://api.example.test/faculty/me/collaboration-requests?status=pending"
  );
});

for (const newToken of ["token-B", "token-A"]) {
  test(`delayed old 401 cannot clear a newer login, even with ${newToken}`, async () => {
    const oldResponse = deferred();
    const headers = [];
    const { api, storage, unauthorized } = makeApi(async (url, options) => {
      headers.push(options.headers.Authorization);
      if (url.endsWith("/auth/login")) {
        return jsonResponse(200, { access_token: newToken });
      }
      return oldResponse.promise;
    }, { storage: memoryStorage({ "researchtwin.sessionToken": "token-A" }) });

    const oldRequest = assert.rejects(api.me(), { kind: "unauthorized", status: 401 });
    await api.login({ email: "new@example.edu", password: "NotStored9" });
    oldResponse.resolve(jsonResponse(401, { detail: "Old session expired" }));
    await oldRequest;

    assert.equal(headers[0], "Bearer token-A");
    assert.equal(storage.getItem("researchtwin.sessionToken"), newToken);
    assert.equal(api.hasSession(), true);
    assert.equal(unauthorized(), 0);
  });
}

test("delayed 401 cannot clear a token replaced directly in session storage", async () => {
  const response = deferred();
  const storage = memoryStorage({ "researchtwin.sessionToken": "token-A" });
  const { api, unauthorized } = makeApi(() => response.promise, { storage });

  const oldRequest = assert.rejects(api.me(), { kind: "unauthorized", status: 401 });
  storage.setItem("researchtwin.sessionToken", "token-B");
  response.resolve(jsonResponse(401, { detail: "Old session expired" }));
  await oldRequest;

  assert.equal(storage.getItem("researchtwin.sessionToken"), "token-B");
  assert.equal(unauthorized(), 0);
});

for (const [status, newToken] of [[200, "token-B"], [401, "token-B"], [503, "token-A"]]) {
  test(`delayed logout (${status}) cannot clear a newer login with ${newToken}`, async () => {
    const oldResponse = deferred();
    const headers = [];
    const { api, storage, unauthorized } = makeApi(async (url, options) => {
      headers.push(options.headers.Authorization);
      if (url.endsWith("/auth/logout")) return oldResponse.promise;
      return jsonResponse(200, { access_token: newToken });
    }, { storage: memoryStorage({ "researchtwin.sessionToken": "token-A" }) });

    const logout = api.logout();
    const finished = status === 200 ? logout : assert.rejects(logout, { status });
    await api.login({ email: "new@example.edu", password: "NotStored9" });
    oldResponse.resolve(jsonResponse(status, { detail: "Old logout completed" }));
    await finished;
    await api.me();

    assert.equal(headers[0], "Bearer token-A");
    assert.equal(headers[2], `Bearer ${newToken}`);
    assert.equal(storage.getItem("researchtwin.sessionToken"), newToken);
    assert.equal(unauthorized(), 0);
  });
}

for (const [firstMethod, secondMethod] of [
  ["login", "login"],
  ["register", "register"],
  ["login", "register"],
  ["register", "login"],
]) {
  test(`reverse ${firstMethod}/${secondMethod} completion rejects the stale auth response`, async () => {
    const responses = [deferred(), deferred()];
    let calls = 0;
    const { api, storage } = makeApi(() => responses[calls++].promise);

    const first = api[firstMethod]({ email: "old@example.edu", password: "NotStored9" });
    const stale = assert.rejects(first, (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.kind, "stale");
      assert.match(error.message, /stale|superseded|newer/i);
      return true;
    });
    const second = api[secondMethod]({ email: "new@example.edu", password: "NotStored9" });
    responses[1].resolve(jsonResponse(200, { access_token: "token-B" }));
    assert.equal((await second).access_token, "token-B");
    responses[0].resolve(jsonResponse(200, { access_token: "token-A" }));
    await stale;

    assert.equal(storage.getItem("researchtwin.sessionToken"), "token-B");
  });
}

test("a failed newer login still supersedes an older pending login", async () => {
  const oldResponse = deferred();
  let calls = 0;
  const { api } = makeApi(() => ++calls === 1
    ? oldResponse.promise
    : Promise.resolve(jsonResponse(401, { detail: "Invalid credentials" })));

  const stale = assert.rejects(api.login({ email: "old@example.edu" }), { kind: "stale" });
  await assert.rejects(api.login({ email: "new@example.edu" }), { kind: "unauthorized" });
  oldResponse.resolve(jsonResponse(200, { access_token: "token-A" }));
  await stale;

  assert.equal(api.hasSession(), false);
});

for (const action of ["clearSession", "logout"]) {
  test(`${action} prevents pending authentication from restoring the session`, async () => {
    const response = deferred();
    const { api } = makeApi(async (url) => url.endsWith("/auth/login")
      ? response.promise
      : jsonResponse(200, { detail: "Logged out" }));

    const stale = assert.rejects(api.login({ email: "old@example.edu" }), { kind: "stale" });
    await api[action]();
    response.resolve(jsonResponse(200, { access_token: "token-A" }));
    await stale;

    assert.equal(api.hasSession(), false);
  });
}

for (const failureTiming of ["initial", "after login"]) {
  test(`storage read failure (${failureTiming}) retains the token in memory`, async () => {
    const storage = memoryStorage();
    const read = storage.getItem;
    let blocked = failureTiming === "initial";
    storage.getItem = (key) => {
      if (blocked) throw new Error("Storage reads blocked");
      return read(key);
    };
    let authorization;
    const { api } = makeApi(async (url, options) => {
      authorization = options.headers.Authorization;
      return jsonResponse(200, { access_token: "memory-token" });
    }, { storage });

    await api.login({ email: "student@example.edu", password: "NotStored9" });
    blocked = true;
    assert.equal(api.hasSession(), true);
    await api.me();
    assert.equal(authorization, "Bearer memory-token");
    api.clearSession();
    blocked = false;
    assert.equal(api.hasSession(), false);
    await api.me();
    assert.equal(authorization, undefined);
  });
}

test("storage write failure uses the new token, not the older persisted token", async () => {
  const storage = memoryStorage({ "researchtwin.sessionToken": "old-token" });
  const writes = [];
  storage.setItem = (key, value) => {
    writes.push([key, value]);
    throw new Error("Storage writes blocked");
  };
  let authorization;
  const { api } = makeApi(async (url, options) => {
    authorization = options.headers.Authorization;
    return jsonResponse(200, { access_token: "memory-token" });
  }, { storage });

  await api.register({ email: "student@example.edu", password: "NotStored9" });
  assert.equal(api.hasSession(), true);
  await api.me();
  assert.equal(authorization, "Bearer memory-token");
  assert.deepEqual(writes, [["researchtwin.sessionToken", "memory-token"]]);
  api.clearSession();
  assert.equal(api.hasSession(), false);
  await api.me();
  assert.equal(authorization, undefined);
});

test("storage removal failure cannot resurrect a cleared session", async () => {
  const storage = memoryStorage({ "researchtwin.sessionToken": "old-token" });
  storage.removeItem = () => { throw new Error("Storage removal blocked"); };
  let authorization;
  const { api } = makeApi(async (url, options) => {
    authorization = options.headers.Authorization;
    return jsonResponse(200, {});
  }, { storage });

  assert.equal(api.hasSession(), true);
  api.clearSession();
  assert.equal(api.hasSession(), false);
  await api.me();
  assert.equal(authorization, undefined);
});

for (const storageMode of ["throwing getter", "absent"]) {
  test(`browser initialization uses memory when sessionStorage is ${storageMode}`, async () => {
    let authorization;
    const window = {
      RESEARCHTWIN_API_BASE: "https://api.example.test",
      fetch: async (url, options) => {
        authorization = options.headers.Authorization;
        return jsonResponse(200, { access_token: "memory-token" });
      },
    };
    if (storageMode === "throwing getter") {
      Object.defineProperty(window, "sessionStorage", {
        get() { throw new Error("Storage access denied"); },
      });
    }
    let api;
    assert.doesNotThrow(() => { api = loadBrowserApi(window); });

    await api.login({ email: "student@example.edu", password: "NotStored9" });
    assert.equal(api.hasSession(), true);
    await api.me();
    assert.equal(authorization, "Bearer memory-token");
    api.clearSession();
    assert.equal(api.hasSession(), false);
  });
}

test("browser initialization still defaults to sessionStorage and stores only tokens", async () => {
  const storage = memoryStorage({ "researchtwin.sessionToken": "existing-token" });
  let authorization;
  const window = {
    RESEARCHTWIN_API_BASE: "https://api.example.test",
    sessionStorage: storage,
    async fetch(url, options) {
      assert.equal(this, window);
      authorization = options.headers.Authorization;
      return jsonResponse(200, { access_token: "new-token" });
    },
  };
  const api = loadBrowserApi(window);

  await api.me();
  assert.equal(authorization, "Bearer existing-token");
  await api.login({ email: "student@example.edu", password: "NotStored9" });
  assert.equal(storage.getItem("researchtwin.sessionToken"), "new-token");
  assert.deepEqual(storage.keys(), ["researchtwin.sessionToken"]);
});

test("missing global fetch does not crash initialization and reports a network error", async () => {
  let api;
  assert.doesNotThrow(() => {
    api = loadBrowserApi({
      RESEARCHTWIN_API_BASE: "https://api.example.test",
      sessionStorage: memoryStorage(),
    });
  });
  await assert.rejects(api.getResearchers(), (error) => {
    assert.equal(error.kind, "network");
    assert.match(error.message, /cannot reach/i);
    return true;
  });
});

test("the request timeout remains active while reading a slow response body", async () => {
  let signal;
  const { api } = makeApi(async (url, options) => {
    signal = options.signal;
    return new Response(new ReadableStream({
      start(controller) {
        const timer = setTimeout(() => {
          controller.enqueue(new TextEncoder().encode("[]"));
          controller.close();
        }, 50);
        signal.addEventListener("abort", () => {
          clearTimeout(timer);
          controller.error(new DOMException("Aborted", "AbortError"));
        }, { once: true });
      },
    }), { status: 200 });
  }, { timeoutMs: 5 });

  await assert.rejects(api.getResearchers(), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.kind, "timeout");
    assert.match(error.message, /timed out/i);
    return true;
  });
  assert.equal(signal.aborted, true);
});

for (const [description, body] of [
  ["HTML", "<html>Proxy failure</html>"],
  ["malformed JSON", '{"id":'],
  ["empty body", ""],
  ["whitespace body", "  \n"],
]) {
  test(`successful HTTP response with ${description} rejects as a protocol error`, async () => {
    const { api } = makeApi(async () => new Response(body, { status: 200 }));

    await assert.rejects(api.me(), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.kind, "protocol");
      assert.equal(error.status, 200);
      assert.match(error.message, /JSON|response/i);
      return true;
    });
  });
}

test("an actual 204 no-content response is allowed", async () => {
  const { api } = makeApi(async () => new Response(null, { status: 204 }));
  assert.equal(await api.saveStudentProfile({ skills: "Python" }), null);
});

for (const status of [200, 503]) {
  test(`body read network failure (${status}) is not swallowed or misclassified`, async () => {
    const { api, unauthorized } = makeApi(async () => new Response(new ReadableStream({
      start(controller) {
        controller.error(new TypeError("Connection reset while reading the body"));
      },
    }), { status }), {
      storage: memoryStorage({ "researchtwin.sessionToken": "valid-token" }),
    });

    await assert.rejects(api.me(), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.kind, "network");
      assert.match(error.message, /reach|network/i);
      return true;
    });
    assert.equal(api.hasSession(), true);
    assert.equal(unauthorized(), 0);
  });
}

// ------------------------------------------------------------------
// API endpoint configuration
// ------------------------------------------------------------------

const configSource = readFileSync(
  require.resolve("../../frontend/frontend-config.js"),
  "utf8"
);

test("configured bases are validated and normalized to an origin", () => {
  for (const [configured, expected] of [
    ["https://api.example.test/", "https://api.example.test"],
    ["https://api.example.test///", "https://api.example.test"],
    ["http://127.0.0.1:8000", "http://127.0.0.1:8000"],
    ["http://localhost:8000/", "http://localhost:8000"],
  ]) {
    const api = createApi({ baseUrl: configured, fetchImpl: async () => {} });
    assert.equal(api.baseUrl, expected, configured);
  }
});

test("invalid API configuration fails closed without issuing a request", async () => {
  for (const baseUrl of [
    "http://api.example.test",
    "https://api.example.test/v1",
    "https://user:secret@api.example.test",
    "ftp://api.example.test",
    "javascript:alert(1)",
    "not a url",
    "",
  ]) {
    let called = false;
    const api = createApi({
      baseUrl,
      fetchImpl: async () => {
        called = true;
        throw new Error("fetch must not run");
      },
    });

    assert.equal(api.baseUrl, "", baseUrl);
    await assert.rejects(api.getResearchers(), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.kind, "configuration");
      return true;
    });
    assert.equal(called, false, baseUrl);
  }
});

test("a deployment with no configuration fails closed", async () => {
  delete globalThis.RESEARCHTWIN_API_BASE;
  const api = createApi({
    fetchImpl: async () => {
      throw new Error("fetch must not run");
    },
  });

  assert.equal(api.baseUrl, "");
  await assert.rejects(
    api.me(),
    (error) => error instanceof ApiError && error.kind === "configuration"
  );
});

test("the production host reaches the reviewed Render endpoint", () => {
  const window = {
    location: { hostname: "starlit-empanada-a323e3.netlify.app" },
  };
  vm.runInNewContext(configSource, { window });

  const api = loadBrowserApi(window);

  assert.equal(api.baseUrl, "https://researchtwin-api.onrender.com");
});

test("an unknown deployment host cannot reach any API", async () => {
  const window = { location: { hostname: "preview.example.test" } };
  vm.runInNewContext(configSource, { window });

  const api = loadBrowserApi(window);

  assert.equal(api.baseUrl, "");
  await assert.rejects(api.getResearchers(), (error) => {
    assert.equal(error.name, "ApiError");
    assert.equal(error.kind, "configuration");
    return true;
  });
});

test("admin endpoints use the documented paths, methods, and query encoding", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, method: options.method, body: options.body });
    return jsonResponse(200, url.includes("/data-export") ? { generated_at: 1 } : []);
  };
  const { api } = makeApi(fetchImpl, {
    storage: memoryStorage({ "researchtwin.sessionToken": "admin-token" }),
  });

  await api.listUsers({ role: "faculty", active: "true", limit: 200 });
  await api.setUserActive(7, false);
  await api.setUserRole(7, "faculty");
  await api.revokeUserSessions(7);
  await api.resetUserPassword(7, "a-long-enough-password");
  await api.exportUserData(7);
  await api.listAuditEvents({ action: "auth.login_failed", target_type: "user", target_id: 7 });
  await api.assignFacultyResearcherLink(7, 12);
  await api.removeFacultyResearcherLink(7);

  assert.deepEqual(calls.map(call => [call.method, call.url]), [
    ["GET", "https://api.example.test/admin/users?role=faculty&active=true&limit=200"],
    ["PUT", "https://api.example.test/admin/users/7/active"],
    ["PUT", "https://api.example.test/admin/users/7/role"],
    ["POST", "https://api.example.test/admin/users/7/sessions/revoke"],
    ["POST", "https://api.example.test/admin/users/7/password-reset"],
    ["GET", "https://api.example.test/admin/users/7/data-export"],
    ["GET", "https://api.example.test/admin/audit-events?action=auth.login_failed&target_type=user&target_id=7"],
    ["PUT", "https://api.example.test/admin/faculty/7/researcher-link"],
    ["DELETE", "https://api.example.test/admin/faculty/7/researcher-link"],
  ]);
  assert.deepEqual(JSON.parse(calls[1].body), { active: false });
  assert.deepEqual(JSON.parse(calls[2].body), { role: "faculty" });
  assert.deepEqual(JSON.parse(calls[4].body), { password: "a-long-enough-password" });
  assert.deepEqual(JSON.parse(calls[7].body), { researcher_id: 12 });
});
