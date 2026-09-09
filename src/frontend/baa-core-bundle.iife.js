(function() {
  "use strict";
  function formatDate(iso) {
    if (!iso) return "-";
    const d = new Date(typeof iso === "number" ? iso * 1e3 : iso);
    if (isNaN(d.getTime())) return "-";
    return d.toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    });
  }
  function maskKey(key) {
    if (!key || key.length <= 8) return key || "";
    return key.slice(0, 4) + "..." + key.slice(-4);
  }
  function escHtml$1(text) {
    const s = String(text ?? "");
    const map = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    };
    return s.replace(/[&<>"']/g, (c) => map[c] || c);
  }
  function permissionBadge(perm) {
    const colors = {
      admin: "bg-red-100 text-red-800",
      write: "bg-blue-100 text-blue-800",
      read: "bg-green-100 text-green-800",
      limited: "bg-gray-100 text-gray-800"
    };
    const c = colors[perm] || "bg-gray-100";
    return `<span class="inline-block px-2 py-0.5 rounded text-xs font-medium ${c}">${escHtml$1(perm)}</span>`;
  }
  function enabledBadge(enabled) {
    if (enabled)
      return '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">✓ 启用</span>';
    return '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">✗ 已禁用</span>';
  }
  function uid() {
    return `id_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  }
  function mergeDeep(target, source) {
    const out = { ...target };
    for (const key in source) {
      if (source[key] && typeof source[key] === "object" && !Array.isArray(source[key])) {
        out[key] = mergeDeep(
          out[key] || {},
          source[key]
        );
      } else {
        out[key] = source[key];
      }
    }
    return out;
  }
  const ICONS = {
    info: "ℹ️",
    success: "✅",
    error: "❌",
    warn: "⚠️"
  };
  function showToast$1(message, type = "info", duration = 4e3) {
    if (typeof message !== "string" || !message) return;
    const container = (() => {
      let c = document.getElementById("toast-container");
      if (!c) {
        c = document.createElement("div");
        c.id = "toast-container";
        c.className = "toast-container";
        document.body.appendChild(c);
      }
      return c;
    })();
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span>${ICONS[type] || "ℹ️"}</span><span>${message}</span>`;
    container.appendChild(toast);
    if (container.children.length > 5) {
      container.firstChild?.remove();
    }
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(20px)";
    }, duration);
    setTimeout(() => {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, duration + 300);
  }
  if (typeof window !== "undefined") {
    window.showToast = showToast$1;
  }
  function showSkeleton(skeletonId, targetId) {
    const skel = document.getElementById(skeletonId);
    if (!skel) return;
    skel.classList.remove("hidden");
    if (targetId) {
      const target = document.getElementById(targetId);
      if (target) target.classList.add("hidden");
    }
  }
  function hideSkeleton(skeletonId, targetId) {
    const skel = document.getElementById(skeletonId);
    if (!skel) return;
    skel.classList.add("hidden");
    if (targetId) {
      const target = document.getElementById(targetId);
      if (target) target.classList.remove("hidden");
    }
  }
  function renderSkeletonContainer(container, rows = 3, className = "skeleton-overlay") {
    if (!container) return;
    const html = Array(rows).fill(0).map(
      () => '<div class="skeleton skeleton-row mb-2"><span class="skeleton-text w-32"></span><span class="skeleton-text flex-1"></span></div>'
    ).join("");
    container.innerHTML = html;
    container.className = className;
    container.classList.remove("hidden");
  }
  function renderProgress(el, label = "处理中", pct = 0) {
    if (!el) return;
    el.className = "review-progress";
    el.innerHTML = `<div class="review-progress-text"><span>${label}</span><span>${pct}%</span></div><div class="review-progress-bar"><div class="review-progress-fill" style="width:${pct}%"></div></div>`;
  }
  let _config = null;
  let _adminToken = "";
  function initApiClient(config) {
    _config = config;
  }
  function setAdminToken(token) {
    _adminToken = token;
  }
  function getApiBase() {
    return _config ? _config.apiBase() : "http://localhost:8000";
  }
  function getReviewHeaders() {
    if (!_config) return {};
    const h = {};
    const key = _config.getActiveKeyValue();
    if (key) h["Authorization"] = "Bearer " + key;
    const teamId = _config.currentTeamId();
    const projectId = _config.currentProjectId();
    if (teamId) h["X-Team-Id"] = teamId;
    if (projectId) h["X-Project-Id"] = projectId;
    return h;
  }
  function getHeaders() {
    return getReviewHeaders();
  }
  function getAdminHeaders(method = "GET") {
    const h = {};
    if (_adminToken) h["Authorization"] = "Bearer " + _adminToken;
    if (method && method !== "GET") h["Content-Type"] = "application/json";
    return h;
  }
  function _errorInfo(r, data) {
    if (typeof data === "object" && data !== null) {
      const d = data;
      if (d.detail) return String(d.detail);
      if (d.message) return String(d.message);
    }
    return JSON.stringify(data || `HTTP ${r.status}`);
  }
  async function _check(r) {
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error("API错误 (" + r.status + "): " + _errorInfo(r, data));
    return data;
  }
  async function apiGet(path) {
    return _check(await fetch(getApiBase() + path, {
      method: "GET",
      headers: getHeaders()
    }));
  }
  async function apiPost(path, body) {
    return apiPostJSON(path, body);
  }
  async function apiPostJSON(path, body) {
    return _check(await fetch(getApiBase() + path, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getHeaders() },
      body: JSON.stringify(body)
    }));
  }
  async function apiFetch(path, options = {}) {
    const r = await fetch(getApiBase() + path, {
      headers: { "Content-Type": "application/json", ...getHeaders(), ...options.headers },
      ...options
    });
    return r.json();
  }
  async function apiPostFile(path, file, extraParams = {}) {
    const form = new FormData();
    form.append("file", file);
    const params = new URLSearchParams(
      Object.fromEntries(Object.entries(extraParams).map(([k, v]) => [k, String(v)]))
    );
    const url = getApiBase() + path + (params.toString() ? "?" + params.toString() : "");
    const r = await fetch(url, {
      method: "POST",
      headers: getReviewHeaders(),
      body: form
    });
    return _check(r);
  }
  async function adminGet(path) {
    return fetch(getApiBase() + path, {
      method: "GET",
      headers: getAdminHeaders("GET")
    }).then((r) => r.json());
  }
  async function adminPost(path, body) {
    return fetch(getApiBase() + path, {
      method: "POST",
      headers: getAdminHeaders("POST"),
      body: JSON.stringify(body)
    }).then((r) => r.json());
  }
  async function adminDelete(path) {
    return fetch(getApiBase() + path, {
      method: "DELETE",
      headers: getAdminHeaders("DELETE")
    }).then((r) => r.json());
  }
  if (typeof window !== "undefined") {
    window.HEADERS = () => getReviewHeaders();
    window.getHeaders = () => getHeaders();
    window.API_BASE = () => getApiBase();
    window.apiGet = apiGet;
    window.apiPostJSON = apiPostJSON;
    window.apiPostFile = apiPostFile;
    window.apiFetch = apiFetch;
    window.adminGet = adminGet;
    window.adminPost = adminPost;
    window.adminDelete = adminDelete;
    window.adminHeaders = (m) => getAdminHeaders(m);
    window.apiPost = (path, body) => apiPostJSON(path, body);
  }
  class AppState {
    constructor() {
      this._teamId = localStorage.getItem("baa_team_id") || "";
      this._projectId = localStorage.getItem("baa_project_id") || "";
      this._historyTeamFilter = "";
      this._historyProjectFilter = "";
      this._currentReviewId = "";
      this._reviewAuditMapping = null;
      this._reviewAuditStates = {};
    }
    get teamId() {
      return this._teamId;
    }
    get projectId() {
      return this._projectId;
    }
    get historyTeamFilter() {
      return this._historyTeamFilter;
    }
    get historyProjectFilter() {
      return this._historyProjectFilter;
    }
    get currentReviewId() {
      return this._currentReviewId;
    }
    get reviewAuditMapping() {
      return this._reviewAuditMapping;
    }
    get reviewAuditStates() {
      return this._reviewAuditStates;
    }
    setTeamId(id) {
      this._teamId = id || "";
      localStorage.setItem("baa_team_id", this._teamId);
    }
    setProjectId(id) {
      this._projectId = id || "";
      localStorage.setItem("baa_project_id", this._projectId);
    }
    setCurrentReviewId(id) {
      this._currentReviewId = id || "";
    }
    setReviewAuditMapping(v) {
      this._reviewAuditMapping = v;
    }
    setReviewAuditStates(v) {
      this._reviewAuditStates = v;
    }
    setHistoryTeamFilter(v) {
      this._historyTeamFilter = v;
    }
    setHistoryProjectFilter(v) {
      this._historyProjectFilter = v;
    }
    loadApiBase() {
      const saved = localStorage.getItem("baa_api_base");
      const input = document.getElementById("api-base");
      if (saved && input) input.value = saved;
    }
    saveApiBase() {
      const input = document.getElementById("api-base");
      if (input) localStorage.setItem("baa_api_base", input.value);
    }
  }
  const appState = new AppState();
  if (typeof window !== "undefined") {
    Object.defineProperty(window, "currentTeamId", {
      get: () => appState.teamId,
      set: (v) => appState.setTeamId(v)
    });
    Object.defineProperty(window, "currentProjectId", {
      get: () => appState.projectId,
      set: (v) => appState.setProjectId(v)
    });
    window.setCurrentTeamId = (id) => appState.setTeamId(id || "");
    window.setCurrentProjectId = (id) => appState.setProjectId(id || "");
    window.getCurrentTeamId = () => appState.teamId;
    window.getCurrentProjectId = () => appState.projectId;
    window.loadApiBase = () => appState.loadApiBase();
    window.saveApiBase = () => appState.saveApiBase();
  }
  async function navigateTo(page) {
    document.querySelectorAll(".sidebar-item").forEach((i) => i.classList.remove("active"));
    document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
    const item = document.querySelector(`.sidebar-item[data-page="${page}"]`);
    const target = document.getElementById(`page-${page}`);
    if (!target) {
      console.warn("Page not found:", page);
      return;
    }
    item?.classList.add("active");
    target.classList.add("active");
    try {
      if (page === "home") {
        await call("loadDashboard");
      } else if (page === "specs") {
        call("loadSpecs");
      } else if (page === "analysis") {
        await call("loadAnalysis");
      } else if (page === "history") {
        call("renderHistoryList");
      } else if (page === "apikeys") {
        await call("loadAdminKeys");
      } else if (page === "cases") {
        call("loadCaseStats");
        call("loadCases", 0);
      } else if (page === "cd") {
        call("loadCDItems");
      } else if (page === "model-params") {
        call("switchModelParamTab", "functions");
      } else if (page === "collab") {
        const token = window.collabToken;
        if (token) {
          call("updateUserStatus", true);
          setTimeout(() => call("collabEnterMain"), 100);
        }
      }
    } catch (e) {
      console.error("页面加载错误:", e);
    }
  }
  function call(fn, ...args) {
    const f = window[fn];
    if (typeof f === "function") return f(...args);
    console.warn(`Function not found: ${fn}`);
    return void 0;
  }
  async function testConnection() {
    const el = document.getElementById("conn-status");
    if (!el) return;
    el.className = "text-xs text-yellow-600";
    el.textContent = "连接中...";
    try {
      const data = await apiGet("/health");
      el.className = "text-xs text-green-600";
      el.textContent = `✅ 连接成功 | ${data.version} | 引擎: ${data.engine_status}`;
    } catch (e) {
      el.className = "text-xs text-red-600";
      el.textContent = `❌ 连接失败: ${e.message}`;
    }
  }
  if (typeof window !== "undefined") {
    window.navigateTo = navigateTo;
    window.testConnection = testConnection;
  }
  const ROUTES = [
    { page: "home", load: () => window.loadDashboard && window.loadDashboard() },
    { page: "specs", load: () => window.loadSpecs && window.loadSpecs() },
    { page: "analysis", load: () => window.loadAnalysis && window.loadAnalysis() },
    { page: "history", load: () => window.renderHistoryList && window.renderHistoryList() },
    { page: "apikeys", load: () => window.loadAdminKeys && window.loadAdminKeys() },
    { page: "cases", load: () => {
      const w2 = window;
      if (typeof w2.loadCaseStats === "function") w2.loadCaseStats();
      if (typeof w2.loadCases === "function") w2.loadCases(0);
    } },
    { page: "cd", load: () => window.loadCDItems && window.loadCDItems() },
    { page: "model-params", load: () => window.switchModelParamTab && window.switchModelParamTab("functions") },
    { page: "collab", load: () => {
      const w2 = window;
      if (w2.collabToken) {
        if (typeof w2.updateUserStatus === "function") w2.updateUserStatus(true);
        setTimeout(() => {
          if (typeof w2.collabEnterMain === "function") w2.collabEnterMain();
        }, 100);
      }
    } },
    { page: "drawings", title: "图纸管理" },
    { page: "review", title: "审查" },
    { page: "compare", title: "对比" },
    { page: "reverse", title: "反向重构" },
    { page: "funcs", title: "原子函数" },
    { page: "settings", title: "设置" },
    { page: "docs", title: "文档" }
  ];
  class Router {
    constructor() {
      this._current = "home";
      this._listeners = [];
      this._popstateBound = null;
      this._popstateBound = () => this._onHashChange();
      window.addEventListener("popstate", this._popstateBound);
      window.addEventListener("hashchange", () => this._onHashChange());
      const initial = this._readHash();
      this._current = initial;
      this._activate(initial, true);
    }
    get current() {
      return this._current;
    }
    /** 编程式导航 */
    go(page) {
      if (page === this._current) return;
      const route = ROUTES.find((r) => r.page === page);
      if (!route) {
        console.warn("No route for:", page);
        return;
      }
      window.location.hash = "#" + page;
    }
    /** 注册页面切换监听 */
    on(listener) {
      this._listeners.push(listener);
      return () => {
        this._listeners = this._listeners.filter((l) => l !== listener);
      };
    }
    _readHash() {
      const hash = window.location.hash.replace("#", "").replace("/", "");
      const route = ROUTES.find((r) => r.page === hash);
      return route ? hash : "home";
    }
    _onHashChange() {
      const page = this._readHash();
      this._activate(page);
    }
    _activate(page, silent = false) {
      this._current = page;
      document.querySelectorAll(".page").forEach((el) => {
        el.classList.toggle("active", el.id === "page-" + page);
      });
      document.querySelectorAll(".sidebar-item").forEach((el) => {
        el.classList.toggle(
          "active",
          el.dataset.page === page
        );
      });
      const route = ROUTES.find((r) => r.page === page);
      if (route?.load) {
        try {
          const result = route.load();
          if (result && typeof result.then === "function") {
            result.catch((e) => {
              console.error("页面加载错误:", page, e);
            });
          }
        } catch (e) {
          console.error("页面加载错误:", page, e);
        }
      }
      if (!silent) {
        this._listeners.forEach((l) => l(page));
      }
    }
  }
  const router = new Router();
  if (typeof window !== "undefined") {
    window.router = router;
  }
  let _keys = [];
  let _activeKey = "";
  function loadKeys() {
    try {
      const stored = localStorage.getItem("baa_api_keys");
      _keys = stored ? JSON.parse(stored) : [];
      _activeKey = localStorage.getItem("baa_active_key") || "";
    } catch {
      _keys = [];
      _activeKey = "";
    }
    populateTokenSelect();
  }
  function saveKeys() {
    localStorage.setItem("baa_api_keys", JSON.stringify(_keys));
  }
  function getActiveKeyValue$1() {
    const k = _keys.find((k2) => k2.id === _activeKey);
    return k ? k.key : "";
  }
  function setActiveKey(id) {
    _activeKey = id;
    localStorage.setItem("baa_active_key", _activeKey);
    populateTokenSelect();
  }
  function populateTokenSelect() {
    const select = document.getElementById("active-key-select");
    if (!select) return;
    select.innerHTML = '<option value="">无令牌（开发模式）</option>';
    _keys.forEach((k) => {
      const opt = document.createElement("option");
      opt.value = k.id;
      opt.textContent = `${k.name} (${maskKey(k.key)})`;
      if (k.id === _activeKey) opt.selected = true;
      select.appendChild(opt);
    });
    const hint = document.getElementById("token-hint");
    if (hint) {
      hint.textContent = _keys.length > 0 ? `共 ${_keys.length} 个本地令牌。外部项目的token可手动添加。` : "暂无令牌。可在「密钥管理」页面创建后在此添加，或点击下方手动输入。";
    }
  }
  function switchApiKey(id) {
    setActiveKey(id);
  }
  function deleteCurrentApiKey() {
    if (!_activeKey) {
      showToast$1("当前没有选中任何令牌", "info");
      return;
    }
    if (!confirm("确认删除当前令牌？")) return;
    deleteApiKey(_activeKey);
  }
  function addApiKey() {
    const name = prompt("令牌名称（如：EMA2对接）");
    if (!name) return;
    const key = prompt("请输入令牌内容（从密钥管理页面复制）");
    if (!key) return;
    _keys.push({ id: `key_${Date.now()}`, name, key, created: Date.now() });
    saveKeys();
    _activeKey = _keys[_keys.length - 1].id;
    localStorage.setItem("baa_active_key", _activeKey);
    populateTokenSelect();
  }
  function deleteApiKey(id) {
    if (!confirm("确认删除此本地令牌？")) return;
    _keys = _keys.filter((k) => k.id !== id);
    if (_activeKey === id) {
      _activeKey = _keys.length > 0 ? _keys[_keys.length - 1].id : "";
      localStorage.setItem("baa_active_key", _activeKey);
    }
    saveKeys();
    populateTokenSelect();
  }
  function copyApiKey(id) {
    const k = _keys.find((k2) => k2.id === id);
    if (!k) return;
    navigator.clipboard.writeText(k.key).then(
      () => showToast$1("令牌已复制到剪贴板", "info"),
      () => showToast$1("复制失败，请手动复制", "error")
    );
  }
  async function refreshTokenSelect() {
    const btn = document.querySelector("#active-key-select + button");
    const hint = document.getElementById("token-hint");
    if (btn) btn.textContent = "⏳";
    if (hint) hint.textContent = "正在从服务端刷新密钥列表...";
    try {
      const data = await apiGet("/admin/keys");
      const keys = data?.data;
      if (keys && keys.length > 0) {
        if (hint) hint.textContent = `✅ 服务端有 ${keys.length} 个已管理密钥。点击「📥 从密钥管理导入」选择并填入。`;
      } else {
        if (hint) hint.textContent = "服务端暂无可用密钥，请先在「密钥管理」页面创建。";
      }
    } catch (e) {
      if (hint) hint.textContent = "❌ 刷新失败: " + e.message + "（请确认当前令牌有admin权限）";
    } finally {
      if (btn) btn.textContent = "🔄";
    }
  }
  if (typeof window !== "undefined") {
    window.getApiKey = () => getActiveKeyValue$1();
    window.getActiveKeyValue = getActiveKeyValue$1;
    window.loadApiKeys = loadKeys;
    window.saveApiKeys = saveKeys;
    window.switchApiKey = switchApiKey;
    window.deleteCurrentApiKey = deleteCurrentApiKey;
    window.addApiKey = addApiKey;
    window.deleteApiKey = deleteApiKey;
    window.copyApiKey = copyApiKey;
    window.populateTokenSelect = populateTokenSelect;
  }
  let _selectedDetailKeyId = "";
  let _detailRawKey = "";
  async function initAdminToken() {
    try {
      const r = await fetch(getApiBase() + "/admin/bootstrap-key");
      if (r.ok) {
        const d = await r.json();
        if (d.status === "success") setAdminToken(d.admin_key || "");
      }
    } catch {
    }
  }
  async function loadAdminKeys() {
    const table = document.getElementById("admin-keys-table");
    if (!table) return;
    table.innerHTML = '<div class="text-center py-8 text-gray-400 text-sm">加载中...</div>';
    try {
      const showDisabled = document.getElementById("show-disabled")?.checked;
      const data = await adminGet(`/admin/keys?include_disabled=${showDisabled ? "true" : "false"}`);
      const statsData = await adminGet("/admin/keys/stats");
      if (statsData?.data && typeof statsData.data === "object" && !Array.isArray(statsData.data)) {
        const s = statsData.data.summary || {};
        ["stat-total", "stat-active", "stat-disabled", "stat-calls"].forEach((id) => {
          const el = document.getElementById(id);
          if (el) el.textContent = String(s[id] ?? 0);
        });
      }
      const items = Array.isArray(data?.data) ? data.data : [];
      if (items.length === 0) {
        table.innerHTML = '<div class="text-center py-8 text-gray-400 text-sm">暂无密钥，点击「+ 创建密钥」开始</div>';
        return;
      }
      let html = '<table class="w-full text-sm"><thead><tr class="text-left text-gray-500 border-b"><th class="pb-2 pr-3">标签</th><th class="pb-2 pr-3">权限</th><th class="pb-2 pr-3">状态</th><th class="pb-2 pr-3">创建</th><th class="pb-2 pr-3">过期</th><th class="pb-2 pr-3">调用</th><th class="pb-2">操作</th></tr></thead><tbody>';
      for (const k of items) {
        const usage = k.usage || {};
        html += `<tr class="border-b hover:bg-gray-50"><td class="py-2 pr-3 font-medium">${escHtml$1(k.label || "-")}</td><td class="py-2 pr-3">${permissionBadge(String(k.permission))}</td><td class="py-2 pr-3">${enabledBadge(Boolean(k.enabled))}</td><td class="py-2 pr-3 text-gray-500">${formatDate(k.created_at)}</td><td class="py-2 pr-3 text-gray-500">${formatDate(k.expires_at)}</td><td class="py-2 pr-3 text-gray-500">${usage.total_calls || 0}</td><td class="py-2"><button onclick="showKeyDetail('${escHtml$1(k.key_id || "")}')" class="px-2 py-1 bg-gray-200 rounded text-xs hover:bg-gray-300 mr-1">详情</button>` + (k.has_raw_key ? `<button onclick="copyKeyFromDetail('${escHtml$1(k.key_id || "")}')" class="px-2 py-1 bg-blue-100 rounded text-xs hover:bg-blue-200 mr-1">📋复制</button>` : "") + (k.enabled ? `<button onclick="confirmRevokeKey('${escHtml$1(k.key_id || "")}')" class="px-2 py-1 bg-red-100 rounded text-xs hover:bg-red-200 mr-1">撤销</button>` : "") + `<button onclick="confirmDeleteKey('${escHtml$1(k.key_id || "")}')" class="px-2 py-1 bg-red-200 rounded text-xs hover:bg-red-300">🗑️</button></td></tr>`;
      }
      table.innerHTML = html + "</tbody></table>";
    } catch (e) {
      table.innerHTML = `<div class="text-center py-8 text-red-500 text-sm">❌ 加载失败: ${escHtml$1(e.message)}</div>`;
    }
  }
  function openCreateKeyModal() {
    document.getElementById("create-key-modal")?.classList.remove("hidden");
    const label = document.getElementById("new-key-label");
    if (label) label.value = "";
    const perm = document.getElementById("new-key-permission");
    if (perm) perm.value = "write";
    const ttl = document.getElementById("new-key-ttl");
    if (ttl) ttl.value = "90";
  }
  function closeCreateKeyModal() {
    document.getElementById("create-key-modal")?.classList.add("hidden");
  }
  async function createAdminKey() {
    const label = (document.getElementById("new-key-label") || {}).value?.trim() || "unnamed";
    const permission = (document.getElementById("new-key-permission") || {}).value || "write";
    const ttl = parseInt((document.getElementById("new-key-ttl") || {}).value || "90");
    const btn = document.querySelector("#create-key-modal .bg-green-600");
    if (btn) {
      btn.textContent = "创建中...";
      btn.disabled = true;
    }
    try {
      const data = await adminPost("/admin/keys", { label, permission, ttl_days: ttl });
      if (data?.status === "success" && data.data && typeof data.data === "object") {
        closeCreateKeyModal();
        const raw = document.getElementById("created-raw-key");
        if (raw) raw.textContent = String(data.data.raw_key || "");
        const info = document.getElementById("created-key-key-info");
        const d = data.data;
        if (info) info.innerHTML = `密钥ID: ${escHtml$1(d.key_id || "-")}<br>权限: ${escHtml$1(d.info?.permission || "-")}<br>过期: ${formatDate(d.info?.expires_at)}`;
        document.getElementById("key-created-modal")?.classList.remove("hidden");
        await loadAdminKeys();
      } else {
        showToast$1(`创建失败: ${JSON.stringify(data?.detail)}`, "error");
      }
    } catch (e) {
      showToast$1(`请求失败: ${e.message}`, "error");
    } finally {
      if (btn) {
        btn.textContent = "创建";
        btn.disabled = false;
      }
    }
  }
  function copyCreatedKey() {
    const txt = document.getElementById("created-raw-key")?.textContent || "";
    navigator.clipboard.writeText(txt).then(() => showToast$1("已复制到剪贴板", "info"));
  }
  function closeKeyCreatedModal() {
    document.getElementById("key-created-modal")?.classList.add("hidden");
  }
  async function showKeyDetail(keyId) {
    _selectedDetailKeyId = keyId;
    _detailRawKey = "";
    const title = document.getElementById("detail-key-title");
    if (title) title.textContent = `密钥详情: ${escHtml$1(keyId)}`;
    document.getElementById("btn-revoke-key")?.classList.add("hidden");
    document.getElementById("btn-show-raw-key")?.classList.add("hidden");
    document.getElementById("detail-raw-key-section")?.classList.add("hidden");
    const content = document.getElementById("key-detail-content");
    if (content) content.innerHTML = '<div class="text-gray-400">加载中...</div>';
    document.getElementById("key-detail-modal")?.classList.remove("hidden");
    try {
      const data = await adminGet(`/admin/keys/${keyId}`);
      if (data?.data && typeof data.data === "object") {
        const k = data.data;
        const usage = k.usage || {};
        if (content)
          content.innerHTML = `<div class="grid grid-cols-2 gap-3"><div><span class="text-gray-500">标签:</span> ${escHtml$1(k.label || "-")}</div><div><span class="text-gray-500">权限:</span> ${permissionBadge(String(k.permission))}</div><div><span class="text-gray-500">状态:</span> ${enabledBadge(Boolean(k.enabled))}</div><div><span class="text-gray-500">创建者:</span> ${escHtml$1(k.created_by || "-")}</div><div><span class="text-gray-500">创建:</span> ${formatDate(k.created_at)}</div><div><span class="text-gray-500">过期:</span> ${formatDate(k.expires_at)}</div><div><span class="text-gray-500">总调用:</span> ${usage.total_calls || 0}</div><div><span class="text-gray-500">最后使用:</span> ${formatDate(usage.last_used)}</div></div>`;
        if (k.raw_key) {
          _detailRawKey = String(k.raw_key);
          document.getElementById("btn-show-raw-key")?.classList.remove("hidden");
        }
        if (k.enabled) document.getElementById("btn-revoke-key")?.classList.remove("hidden");
      }
    } catch (e) {
      if (content) content.innerHTML = `<div class="text-red-500">加载失败: ${escHtml$1(e.message)}</div>`;
    }
  }
  function showDetailRawKey() {
    if (!_detailRawKey) {
      showToast$1("密钥原文不可用（旧版创建的密钥仅初创时可见）", "error");
      return;
    }
    const section = document.getElementById("detail-raw-key-section");
    const val = document.getElementById("detail-raw-key-value");
    if (val) val.textContent = _detailRawKey;
    section?.classList.remove("hidden");
    document.getElementById("btn-show-raw-key")?.classList.add("hidden");
  }
  function copyDetailRawKey() {
    if (!_detailRawKey) return;
    navigator.clipboard.writeText(_detailRawKey).then(
      () => showToast$1("✅ 密钥已复制到剪贴板", "success"),
      () => showToast$1("自动复制失败，请手动 Ctrl+C", "error")
    );
  }
  async function copyKeyFromDetail(keyId) {
    try {
      const data = await adminGet(`/admin/keys/${keyId}`);
      const raw = data?.data?.raw_key;
      if (raw) {
        await navigator.clipboard.writeText(String(raw));
        showToast$1("✅ 密钥已复制到剪贴板", "success");
      } else {
        showToast$1("❌ 密钥原文不可用", "error");
      }
    } catch (e) {
      showToast$1(`❌ 获取密钥失败: ${e.message}`, "error");
    }
  }
  function closeKeyDetailModal() {
    document.getElementById("key-detail-modal")?.classList.add("hidden");
    document.getElementById("detail-raw-key-section")?.classList.add("hidden");
    _detailRawKey = "";
  }
  async function confirmRevokeKey(keyId) {
    if (!confirm(`确认撤销密钥 ${keyId}？`)) return;
    try {
      const data = await adminPost(`/admin/keys/${keyId}/revoke`, {});
      if (data.status === "success") {
        await loadAdminKeys();
        showToast$1("密钥已撤销", "info");
      } else {
        showToast$1(`撤销失败: ${JSON.stringify(data.detail)}`, "error");
      }
    } catch (e) {
      showToast$1(`请求失败: ${e.message}`, "error");
    }
  }
  async function confirmDeleteKey(keyId) {
    if (!confirm(`⚠️ 确认永久删除密钥 ${keyId}？`)) return;
    if (!confirm("再次确认：该密钥将被永久删除，无法找回。")) return;
    try {
      const resp = await adminDelete(`/admin/keys/${keyId}`);
      if (resp.status === "success") {
        await loadAdminKeys();
        showToast$1("密钥已永久删除", "info");
      } else {
        showToast$1(`删除失败: ${JSON.stringify(resp.detail)}`, "error");
      }
    } catch (e) {
      showToast$1(`请求失败: ${e.message}`, "error");
    }
  }
  async function revokeAdminKey() {
    if (_selectedDetailKeyId) {
      await confirmRevokeKey(_selectedDetailKeyId);
      closeKeyDetailModal();
    }
  }
  if (typeof window !== "undefined") {
    window.initAdminToken = initAdminToken;
    window.loadAdminKeys = loadAdminKeys;
    window.openCreateKeyModal = openCreateKeyModal;
    window.closeCreateKeyModal = closeCreateKeyModal;
    window.createAdminKey = createAdminKey;
    window.copyCreatedKey = copyCreatedKey;
    window.closeKeyCreatedModal = closeKeyCreatedModal;
    window.showKeyDetail = showKeyDetail;
    window.showDetailRawKey = showDetailRawKey;
    window.copyDetailRawKey = copyDetailRawKey;
    window.copyKeyFromDetail = copyKeyFromDetail;
    window.closeKeyDetailModal = closeKeyDetailModal;
    window.confirmRevokeKey = confirmRevokeKey;
    window.confirmDeleteKey = confirmDeleteKey;
    window.revokeAdminKey = revokeAdminKey;
  }
  function showDrawingReviewPanel(show) {
    const el = document.getElementById("drawing-review-panel");
    if (!el) return;
    el.classList.toggle("hidden", !show);
    if (show) {
      loadReviewContext();
      const select = document.getElementById("review-drawing-select");
      const parsed = window.parsedDrawings;
      if (select && parsed && parsed.length > 0 && select.options.length <= 1) {
        const refresh = window.refreshDrawingSelect;
        if (typeof refresh === "function") refresh();
      }
    }
  }
  function switchDrawingTab(tab) {
    const btnMap = {
      single: "dr-tab-single",
      batch: "dr-tab-batch",
      multisheet: "dr-tab-multisheet",
      feedback: "dr-tab-feedback",
      thermal: "dr-tab-thermal",
      structural: "dr-tab-structural"
    };
    const panelMap = {
      single: "dr-panel-single",
      batch: "dr-panel-batch",
      multisheet: "dr-panel-multisheet",
      feedback: "dr-panel-feedback",
      thermal: "dr-panel-thermal",
      structural: "dr-panel-structural"
    };
    const sel = "px-3 py-1.5 rounded text-xs font-medium bg-purple-100 text-purple-700";
    const unsel = "px-3 py-1.5 rounded text-xs font-medium bg-gray-100 text-gray-600";
    for (const t in btnMap) {
      const el = document.getElementById(btnMap[t]);
      if (el) el.className = t === tab ? sel : unsel;
    }
    for (const t in panelMap) {
      const el = document.getElementById(panelMap[t]);
      if (el) el.classList.toggle("hidden", t !== tab);
    }
    const w2 = window;
    if (tab === "feedback" && typeof w2.loadFeedbackStats === "function") {
      w2.loadFeedbackStats();
      w2.loadFeedbacks();
    }
    if (tab === "structural" && typeof w2.renderStructuralThresholds === "function") {
      w2.renderStructuralThresholds();
      w2.renderStructuralViolations(window._reviewStructuralViolations || []);
    }
    if (tab === "thermal" && typeof w2.renderThermalThresholds === "function") {
      w2.renderThermalThresholds();
      w2.renderThermalViolations(window._reviewThermalViolations || []);
    }
  }
  async function loadReviewContext() {
    const teamSel = document.getElementById("dr-team-select");
    const projSel = document.getElementById("dr-project-select");
    if (!teamSel || !projSel) return;
    const curTeam = appState.teamId;
    const curProj = appState.projectId;
    try {
      const teamsData = await apiGet("/collab/teams");
      const projectsData = await apiGet("/collab/projects");
      const teams = Array.isArray(teamsData) ? teamsData : teamsData.teams || [];
      const projects = Array.isArray(projectsData) ? projectsData : projectsData.projects || [];
      teamSel.innerHTML = '<option value="">👥 全部团队</option>';
      teams.forEach((t) => {
        const opt = document.createElement("option");
        opt.value = String(t.id);
        opt.textContent = String(t.name);
        if (opt.value === curTeam) opt.selected = true;
        teamSel.appendChild(opt);
      });
      projSel.innerHTML = '<option value="">📋 全部项目</option>';
      projects.forEach((p) => {
        const opt = document.createElement("option");
        opt.value = String(p.id);
        opt.textContent = String(p.name);
        if (opt.value === curProj) opt.selected = true;
        projSel.appendChild(opt);
      });
    } catch {
    }
  }
  function onReviewTeamSelect() {
    const el = document.getElementById("dr-team-select");
    const teamId = el?.value || "";
    appState.setTeamId(teamId);
    appState.setProjectId("");
    const projSel = document.getElementById("dr-project-select");
    if (projSel) projSel.value = "";
  }
  function onReviewProjectSelect() {
    const el = document.getElementById("dr-project-select");
    const projectId = el?.value || "";
    appState.setProjectId(projectId);
  }
  if (typeof window !== "undefined") {
    window.showDrawingReviewPanel = showDrawingReviewPanel;
    window.switchDrawingTab = switchDrawingTab;
    window.loadReviewContext = loadReviewContext;
    window.onReviewTeamSelect = onReviewTeamSelect;
    window.onReviewProjectSelect = onReviewProjectSelect;
  }
  function getActiveKeyValue() {
    const activeId = localStorage.getItem("baa_active_key") || "";
    if (!activeId) return "";
    try {
      const keys = JSON.parse(localStorage.getItem("baa_api_keys") || "[]");
      const k = keys.find((k2) => String(k2.id) === activeId);
      return k ? String(k.key || "") : "";
    } catch {
      return "";
    }
  }
  async function importServerKey() {
    const activeKeyVal = getActiveKeyValue();
    if (!activeKeyVal) {
      if (!confirm(
        "当前未选择任何令牌，后端 /admin/keys 需要admin权限。\n是否仍要尝试？（建议先在「密钥管理」创建admin密钥后选择）"
      )) {
        return;
      }
    }
    const list = document.getElementById("import-key-list");
    if (!list) {
      showToast$1("页面元素异常", "info");
      return;
    }
    list.innerHTML = '<div class="text-center text-gray-400 text-sm py-4">⏳ 加载中...</div>';
    const modal = document.getElementById("import-key-modal");
    modal?.classList.remove("hidden");
    try {
      const data = await apiGet("/admin/keys");
      const keys = data?.data;
      if (!keys || keys.length === 0) {
        list.innerHTML = '<div class="text-center text-gray-400 text-sm py-4">暂无可用密钥，请先在「密钥管理」页面创建。</div>';
        return;
      }
      const detail = data?.detail;
      if (detail && detail.error_code === "FORBIDDEN") {
        list.innerHTML = '<div class="text-center text-red-500 text-sm py-4">❌ 权限不足：当前令牌无admin权限。\n请先在「密钥管理」页面创建admin密钥，\n然后在连接配置页选择该令牌后再试。</div>';
        return;
      }
      list.innerHTML = "";
      for (const k of keys) {
        if (!k.enabled) continue;
        const div = document.createElement("div");
        const label = escHtml$1(String(k.label || k.key_id));
        const expires = k.expires_at ? "过期: " + formatDate(String(k.expires_at)) : "永不过期";
        const keyId = escHtml$1(String(k.key_id || ""));
        div.className = "flex items-center justify-between p-3 border rounded-lg hover:bg-gray-50 cursor-pointer";
        div.innerHTML = `<div class="flex-1 min-w-0"><div class="font-medium text-sm">${label}</div><div class="text-xs text-gray-400">权限: ${escHtml$1(String(k.permission))} | ${expires}</div></div><button onclick="importSelectedKey('${keyId}')" class="px-3 py-1.5 bg-purple-600 text-white rounded text-xs hover:bg-purple-700 shrink-0">选择并填入</button>`;
        list.appendChild(div);
      }
    } catch (e) {
      list.innerHTML = `<div class="text-center text-red-500 text-sm py-4">❌ 加载失败: ${escHtml$1(e.message)}</div>`;
    }
  }
  async function importSelectedKey(keyId) {
    const keyValue = prompt(`请输入此密钥的原始值（从密钥管理页创建时复制）：`);
    if (!keyValue) return;
    const btn = event?.target || document.querySelector("#import-key-modal button");
    if (btn) {
      btn.textContent = "验证中...";
      btn.disabled = true;
    }
    try {
      const verifyResult = await apiPostJSON("/admin/keys/verify", { raw_key: keyValue });
      const vr = verifyResult;
      if (vr.status === "success" && vr.valid) {
        const keyInfo = vr.key_info || {};
        const label = String(keyInfo.label || keyInfo.key_id || keyId) + " (imported)";
        const id = `key_${Date.now()}`;
        const stored = localStorage.getItem("baa_api_keys");
        const keys = stored ? JSON.parse(stored) : [];
        keys.push({ id, name: label, key: keyValue, created: Date.now() });
        localStorage.setItem("baa_api_keys", JSON.stringify(keys));
        localStorage.setItem("baa_active_key", id);
        const populate = window.populateTokenSelect;
        if (typeof populate === "function") populate();
        closeImportKeyModal();
        showToast$1("✅ 密钥验证通过，已添加到本地令牌列表", "success");
      } else {
        showToast$1(
          "❌ 密钥验证失败：" + String(vr.message || "密钥无效或已过期"),
          "error"
        );
      }
    } catch (e) {
      if (confirm("无法验证密钥有效性（" + e.message + "）。是否仍要保存到本地？")) {
        const id = `key_${Date.now()}`;
        const stored = localStorage.getItem("baa_api_keys");
        const keys = stored ? JSON.parse(stored) : [];
        keys.push({ id, name: keyId + " (imported)", key: keyValue, created: Date.now() });
        localStorage.setItem("baa_api_keys", JSON.stringify(keys));
        localStorage.setItem("baa_active_key", id);
        const populate = window.populateTokenSelect;
        if (typeof populate === "function") populate();
        closeImportKeyModal();
      }
    } finally {
      if (btn) {
        btn.textContent = "选择并填入";
        btn.disabled = false;
      }
    }
  }
  function closeImportKeyModal() {
    document.getElementById("import-key-modal")?.classList.add("hidden");
  }
  if (typeof window !== "undefined") {
    const w2 = window;
    w2.importServerKey = importServerKey;
    w2.importSelectedKey = importSelectedKey;
    w2.closeImportKeyModal = closeImportKeyModal;
  }
  let _activeModalId = 0;
  const _sizeCls = {
    sm: "max-w-sm",
    md: "max-w-md",
    lg: "max-w-lg",
    xl: "max-w-2xl"
  };
  function openModal(options) {
    const id = options.id || `modal-${++_activeModalId}`;
    const size = _sizeCls[options.size || "md"];
    let overlay = document.getElementById(id);
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = id;
      overlay.className = "fixed inset-0 bg-black/40 flex items-center justify-center z-50 transition-opacity duration-200";
      overlay.style.opacity = "0";
      overlay.style.pointerEvents = "none";
      document.body.appendChild(overlay);
    }
    const title = options.title || "";
    const footerHtml = options.footerButtons ? options.footerButtons.map(
      (b) => `<button class="px-3 py-1.5 rounded text-xs ${b.cls || "bg-gray-600 text-white hover:bg-gray-700"}" data-btn="${b.label}">${b.label}</button>`
    ).join(" ") : "";
    let contentHtml = "";
    if (typeof options.content === "string") {
      contentHtml = options.content;
    } else if (options.content instanceof HTMLElement) {
      const wrapper = document.createElement("div");
      wrapper.appendChild(options.content.cloneNode(true));
      contentHtml = wrapper.innerHTML;
    }
    overlay.innerHTML = `<div class="bg-white rounded-lg shadow-xl w-full mx-4 ${size} max-h-[90vh] overflow-y-auto">` + (title ? `<div class="flex items-center justify-between p-4 border-b"><h3 class="text-sm font-medium">${title}</h3><button class="text-gray-400 hover:text-gray-600 text-lg" data-close>&times;</button></div>` : "") + `<div class="p-4">${contentHtml}</div>` + (footerHtml ? `<div class="flex justify-end gap-2 p-4 border-t bg-gray-50">${footerHtml}</div>` : "") + `</div>`;
    overlay.querySelectorAll("[data-close]").forEach((btn) => {
      btn.addEventListener("click", () => closeModal(id, options));
    });
    if (options.closeOnOverlay) {
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) closeModal(id, options);
      });
    }
    if (options.footerButtons) {
      overlay.querySelectorAll("[data-btn]").forEach((btn) => {
        const label = btn.dataset.btn || "";
        const match = options.footerButtons?.find((b) => b.label === label);
        if (match) {
          btn.addEventListener("click", () => {
            match.onClick();
          });
        }
      });
    }
    requestAnimationFrame(() => {
      overlay.style.opacity = "1";
      overlay.style.pointerEvents = "auto";
    });
    return () => closeModal(id, options);
  }
  function closeModal(id, options) {
    const overlay = document.getElementById(id);
    if (!overlay) return;
    overlay.style.opacity = "0";
    overlay.style.pointerEvents = "none";
    setTimeout(() => overlay.remove(), 200);
    options.onClose?.();
  }
  if (typeof window !== "undefined") {
    window.openModal = openModal;
  }
  let _parsedDrawings = [];
  const _fileCache = {};
  function getParsedDrawings() {
    return _parsedDrawings;
  }
  function setParsedDrawings(v) {
    _parsedDrawings = v;
    if (typeof window !== "undefined") window.parsedDrawings = v;
  }
  function setFileCache(id, file) {
    _fileCache[id] = file;
    if (typeof window !== "undefined") window.fileCache = _fileCache;
  }
  let _specData = [];
  function getSpecData() {
    return _specData;
  }
  function setSpecData(specs) {
    _specData = specs;
  }
  if (typeof window !== "undefined") {
    Object.defineProperty(window, "SPEC_DATA", {
      get: () => _specData,
      set: (v) => {
        _specData = v;
      }
    });
  }
  let _reviewResults = [];
  function getReviewResults$1() {
    return _reviewResults;
  }
  async function loadReviewResults() {
    const apiBase = getApiBase();
    const teamFilter = document.getElementById("history-team-filter")?.value || "";
    const projFilter = document.getElementById("history-project-filter")?.value || "";
    let params = "limit=200";
    if (teamFilter) params += "&team_id=" + encodeURIComponent(teamFilter);
    if (projFilter) params += "&project_id=" + encodeURIComponent(projFilter);
    try {
      const r = await fetch(apiBase + "/review/history?" + params, {
        method: "GET",
        headers: getHeaders()
      });
      const data = await r.json();
      if (data && data.items && data.items.length > 0) {
        _reviewResults = data.items;
        try {
          localStorage.setItem("baa_review_results", JSON.stringify(_reviewResults));
        } catch (_e) {
        }
        return;
      }
      fallbackLoadReviewResults();
    } catch (_e) {
      fallbackLoadReviewResults();
    }
  }
  function fallbackLoadReviewResults() {
    try {
      const stored = localStorage.getItem("baa_review_results");
      if (stored) _reviewResults = JSON.parse(stored);
    } catch (_e) {
      _reviewResults = [];
    }
  }
  function refreshCompareDrawingSelect() {
    const select = document.getElementById("compare-drawing-select");
    if (!select) return;
    select.innerHTML = '<option value="">— 选择已审查图纸 —</option>';
    _reviewResults.forEach((r) => {
      const opt = document.createElement("option");
      opt.value = r.id || "";
      opt.textContent = (r.drawingName || "") + " (" + (r.buildingType === "civil" ? "民用" : "工业") + ") - " + ((r.details || []).length || 0) + "项违规";
      select.appendChild(opt);
    });
  }
  async function loadDashboard() {
    try {
      const health = await apiGet("/health");
      const verEl = document.getElementById("version-info");
      const hsEl = document.getElementById("health-status");
      if (verEl) verEl.textContent = String(health.version || "") + " · 引擎就绪";
      if (hsEl) hsEl.textContent = JSON.stringify(health, null, 2);
      await loadReviewResults();
      const results = getReviewResults$1();
      const stats = document.getElementById("home-stats");
      if (stats) {
        const cards = stats.querySelectorAll(".stat-card");
        const el0 = cards[0] && cards[0].querySelector(".text-2xl");
        if (el0) el0.textContent = String(results.length);
        const specData = getSpecData();
        const el1 = cards[1] && cards[1].querySelector(".text-2xl");
        if (el1) el1.textContent = String(specData.length);
        if (results.length > 0) {
          const totalV = results.reduce((s, r) => s + (Array.isArray(r.details) ? r.details.length : 0), 0);
          const totalC = results.reduce((s, r) => {
            const sm = r.summary;
            return s + (sm && typeof sm === "object" ? Number(sm.total_checks || 0) : 0);
          }, 0);
          const passRate = totalC > 0 ? Math.round((1 - totalV / totalC) * 100) + "%" : "--";
          const el2 = cards[2] && cards[2].querySelector(".text-2xl");
          if (el2) el2.textContent = passRate;
          const el3 = cards[3] && cards[3].querySelector(".text-2xl");
          if (el3) el3.textContent = String(results[0].drawingName || "");
        }
      }
      renderRecentReviews();
      renderSpecFreqBars();
      renderViolationTypeBars();
    } catch (e) {
      const verEl = document.getElementById("version-info");
      const hsEl = document.getElementById("health-status");
      if (verEl) verEl.textContent = "⚠️ 服务未连接";
      if (hsEl) hsEl.textContent = "连接失败: " + e.message;
    }
  }
  function renderRecentReviews() {
    const el = document.getElementById("recent-reviews");
    if (!el) return;
    const results = getReviewResults$1();
    if (results.length === 0) {
      el.innerHTML = '<div class="text-xs text-gray-400">暂无审查记录</div>';
      return;
    }
    const recent = results.slice(0, 5);
    el.innerHTML = recent.map((r) => {
      const rr = r;
      const v = rr.details?.length || 0;
      const color = v === 0 ? "green" : "red";
      return '<div class="flex items-center justify-between py-1 border-b border-gray-50 last:border-0"><span class="font-medium">' + escHtml$1(String(rr.drawingName || "")) + '</span><span class="text-' + color + '-600">' + v + " 项违规</span></div>";
    }).join("");
  }
  function renderSpecFreqBars() {
    const el = document.getElementById("spec-freq-bars");
    if (!el || getReviewResults$1().length === 0) return;
    const freq = {};
    getReviewResults$1().forEach((r) => {
      const rr = r;
      (rr.details || []).forEach((v) => {
        const key = String(v.clause_id || "未知");
        freq[key] = (freq[key] || 0) + 1;
      });
    });
    const sorted = Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 8);
    const maxVal = Math.max(...sorted.map((s) => s[1]), 1);
    el.innerHTML = sorted.map(
      ([k, v]) => '<div class="flex items-center gap-2"><span class="w-24 truncate">' + escHtml$1(k) + '</span><div class="flex-1 bg-gray-100 rounded-full h-3"><div class="bg-blue-500 h-3 rounded-full" style="width:' + v / maxVal * 100 + '%"></div></div><span class="w-6 text-right">' + v + "</span></div>"
    ).join("");
  }
  function renderViolationTypeBars() {
    const el = document.getElementById("violation-type-bars");
    if (!el || getReviewResults$1().length === 0) return;
    const freq = {};
    const labels = { critical: "严重", major: "主要", minor: "轻微" };
    getReviewResults$1().forEach((r) => {
      const rr = r;
      (rr.details || []).forEach((v) => {
        const key = labels[String(v.severity || "major")] || "未知";
        freq[key] = (freq[key] || 0) + 1;
      });
    });
    const colors = { "严重": "#ef4444", "主要": "#f97316", "轻微": "#eab308" };
    const total = Object.values(freq).reduce((a, b) => a + b, 0) || 1;
    el.innerHTML = Object.entries(freq).map(
      ([k, v]) => '<div class="flex items-center gap-2"><span class="w-10">' + escHtml$1(k) + '</span><div class="flex-1 bg-gray-100 rounded-full h-3"><div class="h-3 rounded-full" style="width:' + v / total * 100 + "%;background:" + (colors[k] || "#6b7280") + '"></div></div><span class="w-6 text-right">' + v + "</span></div>"
    ).join("");
  }
  function saveParsedDrawings() {
    try {
      localStorage.setItem("baa_parsed_drawings", JSON.stringify(getParsedDrawings()));
    } catch (_e) {
    }
  }
  function loadParsedDrawings() {
    try {
      const stored = localStorage.getItem("baa_parsed_drawings");
      if (stored) setParsedDrawings(JSON.parse(stored));
    } catch (_e) {
      setParsedDrawings([]);
    }
  }
  function renderDrawingList() {
    const tbody = document.getElementById("drawing-list");
    if (!tbody) return;
    const list = getParsedDrawings();
    const countEl = document.getElementById("drawing-count");
    if (countEl) countEl.textContent = String(list.length);
    if (list.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="py-8 text-center text-gray-300">暂无记录，请上传图纸</td></tr>';
      return;
    }
    tbody.innerHTML = list.map((d, i) => {
      const yoloBadge = d.use_yolo ? '<span class="ml-1 px-1 py-0.5 bg-purple-100 text-purple-700 rounded text-xs">YOLO</span>' : "";
      const checked = d._selected ? "checked" : "";
      const elements = d.elements;
      return '<tr class="border-b border-gray-50 text-sm"><td class="py-2 px-2"><input type="checkbox" class="drawing-select" data-idx="' + i + '" ' + checked + ' onchange="toggleDrawingSelect(' + i + ',this.checked)" /></td><td class="py-2 px-2 truncate max-w-32">' + escHtml$1(String(d.filename)) + yoloBadge + '</td><td class="py-2 px-2 text-xs">' + (d.building_type === "civil" ? "民用" : "工业") + '</td><td class="py-2 px-2">' + (elements?.length || 0) + '</td><td class="py-2 px-2 text-xs max-w-40 truncate">' + (elements ? elements.map((e) => e.type).join(", ") : "") + '</td><td class="py-2 px-2 text-xs">' + new Date(String(d.parsedAt)).toLocaleTimeString() + '</td><td class="py-2 px-2"><button onclick="sendToReview(' + i + ')" class="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs hover:bg-blue-200 mr-1">送审</button>' + (d.file_id ? `<button onclick="downloadReviewPdf('` + escHtml$1(String(d.file_id)) + `')" class="px-2 py-0.5 bg-red-100 text-red-700 rounded text-xs hover:bg-red-200 mr-1" title="下载PDF报告">📄</button>` : "") + '<button onclick="deleteDrawing(' + i + ')" class="px-2 py-0.5 bg-red-100 text-red-700 rounded text-xs hover:bg-red-200">🗑️</button></td></tr>';
    }).join("");
    updateBatchButton();
  }
  function toggleDrawingSelect(idx, checked) {
    const list = getParsedDrawings();
    if (list[idx]) list[idx]._selected = checked;
    updateBatchButton();
  }
  function selectAllDrawings() {
    getParsedDrawings().forEach((d) => d._selected = true);
    renderDrawingList();
  }
  function deselectAllDrawings() {
    getParsedDrawings().forEach((d) => d._selected = false);
    renderDrawingList();
  }
  function updateBatchButton() {
    const count = getParsedDrawings().filter((d) => d._selected).length;
    const btn = document.getElementById("batch-review-btn");
    const badge = document.getElementById("batch-count");
    if (btn) {
      btn.className = count > 0 ? "px-3 py-1 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700" : "px-3 py-1 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 hidden";
    }
    if (badge) badge.textContent = String(count);
  }
  async function uploadDrawing() {
    const file = document.getElementById("file-input")?.files?.[0];
    if (!file) {
      showToast$1("请先选择图纸文件", "info");
      return;
    }
    const ext = file.name.split(".").pop()?.toLowerCase() || "";
    if (ext !== "dxf") {
      showToast$1("仅支持 .dxf 格式。DWG 格式兼容性有限，请先用CAD转存为DXF。", "warn");
      return;
    }
    const bt = document.getElementById("drawing-bt")?.value || "";
    const progress = document.getElementById("upload-progress");
    if (progress) {
      progress.className = "card mb-4";
      progress.innerHTML = '<div class="review-progress"><div class="review-progress-text"><span>解析</span><span>0%</span></div><div class="review-progress-bar"><div class="review-progress-fill" style="width:0%"></div></div></div>';
    }
    try {
      const useYolo = document.getElementById("use-yolo-checkbox")?.checked || false;
      const yoloDevice = document.getElementById("yolo-device-select")?.value || "cpu";
      const result = await apiPostFile("/deconstruct", file, { building_type: bt, use_yolo: useYolo, yolo_device: yoloDevice });
      if (progress) progress.className = "hidden";
      const fileId = String(result.file_id || "drawing_" + Date.now());
      setFileCache(fileId, file);
      const entry = {
        id: fileId,
        filename: file.name,
        building_type: bt,
        parsedAt: (/* @__PURE__ */ new Date()).toISOString(),
        elements: result.elements || [],
        entities: result.entities || [],
        findings_count: result.findings || 0,
        total_checks: result.total_checks || 0,
        file_id: fileId,
        raw: result,
        use_yolo: useYolo
      };
      const list = getParsedDrawings();
      list.unshift(entry);
      setParsedDrawings(list);
      saveParsedDrawings();
      renderDrawingList();
      const preview = document.getElementById("drawing-preview");
      if (preview) preview.className = "card";
      const jsonEl = document.getElementById("parse-result-json");
      if (jsonEl) jsonEl.textContent = JSON.stringify(result, null, 2);
      const renderImg = document.getElementById("drawing-render-img");
      const placeholder = document.getElementById("drawing-render-placeholder");
      if (renderImg) {
        renderImg.className = "w-full";
        renderImg.src = getApiBase() + "/render/" + fileId;
      }
      if (placeholder) placeholder.className = "hidden";
      refreshReviewDrawingSelect();
      loadDashboard();
    } catch (e) {
      if (progress) {
        progress.innerHTML = "❌ 解析失败: " + String(e);
        progress.className = "card mb-4 text-sm text-red-500";
      }
    }
  }
  async function uploadAndReview() {
    const file = document.getElementById("file-input")?.files?.[0];
    if (!file) {
      showToast$1("请先选择图纸文件", "info");
      return;
    }
    const ext = file.name.split(".").pop()?.toLowerCase() || "";
    if (ext !== "dxf" && ext !== "dwg") {
      showToast$1("仅支持 .dxf 和 .dwg 格式", "warn");
      return;
    }
    const bt = document.getElementById("drawing-bt")?.value || "";
    const progress = document.getElementById("upload-progress");
    if (progress) {
      progress.className = "card mb-4 text-sm text-gray-500";
      progress.innerHTML = '<div class="review-progress"><div class="review-progress-text"><span>解析</span><span>0%</span></div><div class="review-progress-bar"><div class="review-progress-fill" style="width:0%"></div></div></div>';
    }
    try {
      const useYolo = document.getElementById("use-yolo-checkbox")?.checked || false;
      const yoloDevice = document.getElementById("yolo-device-select")?.value || "cpu";
      const result = await apiPostFile("/deconstruct", file, { building_type: bt, use_yolo: useYolo, yolo_device: yoloDevice });
      if (progress) progress.className = "hidden";
      const fileId = String(result.file_id || "drawing_" + Date.now());
      setFileCache(fileId, file);
      const entry = {
        id: fileId,
        filename: file.name,
        building_type: bt,
        parsedAt: (/* @__PURE__ */ new Date()).toISOString(),
        elements: result.elements || [],
        entities: result.entities || [],
        findings_count: result.findings || 0,
        total_checks: result.total_checks || 0,
        use_yolo: useYolo,
        file_id: fileId,
        raw: result
      };
      const list = getParsedDrawings();
      list.unshift(entry);
      setParsedDrawings(list);
      saveParsedDrawings();
      renderDrawingList();
      refreshReviewDrawingSelect();
      loadDashboard();
      const preview = document.getElementById("drawing-preview");
      if (preview) {
        preview.className = "card";
        const jsonEl = document.getElementById("parse-result-json");
        if (jsonEl) jsonEl.textContent = JSON.stringify(result, null, 2);
      }
    } catch (e) {
      if (progress) {
        progress.innerHTML = "❌ 解析失败: " + String(e);
        progress.className = "card mb-4 text-sm text-red-500";
      }
    }
  }
  async function batchReview() {
    const selected = getParsedDrawings().filter((d) => d._selected);
    if (selected.length === 0) {
      showToast$1("请先勾选要送审的图纸", "info");
      return;
    }
    const progress = document.getElementById("upload-progress");
    if (progress) {
      progress.className = "card mb-4";
      progress.innerHTML = '<div class="review-progress"><div class="review-progress-text"><span>批量审查</span><span>0%</span></div><div class="review-progress-bar"><div class="review-progress-fill" style="width:0%"></div></div></div>';
    }
    let totalViolations = 0;
    const results = [];
    for (const d of selected) {
      try {
        const r = await apiPost("/review-from-data", {
          entities: d.elements || [],
          building_type: d.building_type
        });
        if (r.status === "completed" || r.status === "success") {
          const v = r.details?.length || 0;
          totalViolations += v;
          results.push({ name: d.filename, violations: v, details: r.details });
        }
      } catch (e) {
        results.push({ name: d.filename, violations: -1, error: String(e) });
      }
    }
    if (progress) {
      progress.className = "card mb-4 text-sm";
      let html = "✅ 批量审查完成 (" + selected.length + " 张, 共 " + totalViolations + " 项违规)<br/><br/>";
      for (const r of results) {
        if (r.error) {
          html += '<div class="text-red-500 text-xs">❌ ' + escHtml$1(String(r.name)) + ": " + escHtml$1(String(r.error)) + "</div>";
        } else {
          const c = Number(r.violations) > 0 ? "text-red-500" : "text-green-600";
          html += '<div class="text-xs mb-1">' + escHtml$1(String(r.name)) + ': <span class="' + c + '">' + r.violations + " 项违规</span></div>";
        }
      }
      progress.innerHTML = html;
    }
    if (results.length > 0) {
      const fn = window.switchPage;
      fn?.("review");
    }
  }
  function deleteDrawing(idx) {
    const list = getParsedDrawings();
    const d = list[idx];
    if (!d) return;
    if (!confirm("确定删除图纸「" + d.filename + "」的解析记录？")) return;
    list.splice(idx, 1);
    setParsedDrawings(list);
    saveParsedDrawings();
    renderDrawingList();
  }
  function sendToReview(idx) {
    const d = getParsedDrawings()[idx];
    if (!d) return;
    document.querySelectorAll(".sidebar-item").forEach((el) => el.classList.remove("active"));
    const target = document.querySelector('[data-page="review"]');
    if (target) target.classList.add("active");
    document.querySelectorAll(".page").forEach((el) => el.classList.remove("active"));
    const page = document.getElementById("page-review");
    if (page) page.classList.add("active");
    const select = document.getElementById("review-drawing-select");
    if (!select) return;
    for (let i = 0; i < select.options.length; i++) {
      if (select.options[i].value === String(d.id)) {
        select.selectedIndex = i;
        break;
      }
    }
    onReviewDrawingSelect();
  }
  function refreshReviewDrawingSelect() {
    const select = document.getElementById("review-drawing-select");
    if (!select) return;
    select.innerHTML = '<option value="">— 选择已解析图纸 —</option>';
    getParsedDrawings().forEach((d) => {
      const opt = document.createElement("option");
      opt.value = String(d.id);
      opt.textContent = d.filename + " (" + (d.building_type === "civil" ? "民用" : "工业") + ")";
      select.appendChild(opt);
    });
  }
  function onReviewDrawingSelect() {
    const select = document.getElementById("review-drawing-select");
    const btn = document.getElementById("review-start-btn");
    const info = document.getElementById("review-drawing-info");
    const id = select?.value || "";
    if (!id || !btn || !info) {
      btn && (btn.disabled = true);
      info && (info.textContent = "");
      return;
    }
    const d = getParsedDrawings().find((p) => p.id === id);
    if (!d) {
      btn.disabled = true;
      info.textContent = "";
      return;
    }
    btn.disabled = false;
    info.textContent = "实体: " + (d.elements?.length || 0) + "个 · 已解析: " + new Date(String(d.parsedAt)).toLocaleString();
  }
  async function loadSpecs() {
    try {
      const r = await fetch(getApiBase() + "/api/v1/specs", { headers: getHeaders() });
      const data = await r.json();
      if (data.status === "ok") {
        setSpecData(data.specs);
      }
    } catch (e) {
      console.warn("规范库加载失败", e);
    }
    renderSpecList();
    const statsEl = document.getElementById("home-stats");
    const specCount = statsEl?.querySelectorAll(".stat-card")[1]?.querySelector(".text-2xl");
    if (specCount) specCount.textContent = String((getSpecData() || []).length);
  }
  function renderSpecList(_showAll = false) {
    const tbody = document.getElementById("spec-list");
    if (!tbody) return;
    const search = document.getElementById("spec-search")?.value || "";
    const levelFilter = document.getElementById("spec-filter-level")?.value || "all";
    const catFilter = document.getElementById("spec-filter-cat")?.value || "all";
    const stdFilter = document.getElementById("spec-filter-std")?.value || "all";
    const specs = getSpecData() || [];
    const total = specs.length;
    const l1 = specs.filter((s) => String(s.level || "L1") === "L1").length;
    const l2 = specs.filter((s) => String(s.level || "L1") === "L2").length;
    const l3 = specs.filter((s) => String(s.level || "L1") === "L3").length;
    const tc = document.getElementById("spec-total-count");
    if (tc) tc.textContent = String(total);
    const l1c = document.getElementById("spec-l1-count");
    if (l1c) l1c.textContent = String(l1);
    const l2c = document.getElementById("spec-l2-count");
    if (l2c) l2c.textContent = String(l2);
    const l3c = document.getElementById("spec-l3-count");
    if (l3c) l3c.textContent = String(l3);
    let filtered = specs;
    if (levelFilter !== "all") filtered = filtered.filter((s) => String(s.level || "L1") === levelFilter);
    if (catFilter !== "all") filtered = filtered.filter((s) => (s.category || "") === catFilter);
    if (stdFilter !== "all") {
      filtered = filtered.filter((s) => {
        const std = String(s.standard || s.std || "");
        return std.toLowerCase().includes(stdFilter.toLowerCase());
      });
    }
    if (search) {
      const q = search.toLowerCase();
      filtered = filtered.filter(
        (s) => String(s.clause_id || "").toLowerCase().includes(q) || String(s.title || s.name || "").toLowerCase().includes(q) || String(s.text || s.description || "").toLowerCase().includes(q) || String(s.standard || s.std || "").toLowerCase().includes(q)
      );
    }
    const fcount = document.getElementById("spec-filter-count");
    if (fcount) fcount.textContent = filtered.length + " 条" + (filtered.length < total ? " / " + total : "");
    if (filtered.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="py-8 text-center text-gray-300">无匹配记录</td></tr>';
      return;
    }
    const catLabels = { fire_safety: "防火安全", evacuation: "疏散", lighting: "照明", structure: "结构", hvac: "暖通" };
    const levelColors = { L1: "red", L2: "orange", L3: "green" };
    const stdAbbrev = {
      "GB 50016-2014": "016",
      "GB 50016-2018": "016",
      "GB 50974-2014": "974",
      "GB 50763-2012": "763",
      "GB 50067-2014": "067",
      "GB 50116-2013": "116",
      "GB 50084-2017": "084",
      "NFPA 101-2021": "NFPA101",
      "NFPA 5000-2021": "NFPA5K"
    };
    tbody.innerHTML = filtered.map((s, i) => {
      const title = s.title || s.name || "";
      const desc = s.text || s.description || "";
      const cat = String(s.category || "--");
      const target = s.func_id || "--";
      const level = String(s.level || "L1");
      const std = String(s.standard || s.std || "");
      const stdShort = stdAbbrev[std] || (std ? std.replace(/-/g, "").slice(0, 5) : "--");
      const targetStr = Array.isArray(target) ? target.join(", ") : String(target);
      return '<tr class="border-b border-gray-50"><td class="py-2 px-2 text-xs">' + (i + 1) + '</td><td class="py-2 px-2 font-mono text-xs">' + escHtml$1(String(s.clause_id || "")) + '</td><td class="py-2 px-2 text-sm">' + escHtml$1(String(title)) + '<br/><span class="text-xs text-gray-400">' + escHtml$1(String(desc)) + '</span></td><td class="py-2 px-2 text-xs">' + (std ? '<span class="bg-blue-100 text-blue-700 px-1 rounded">' + escHtml$1(stdShort) + "</span>" : "") + '</td><td class="py-2 px-2"><span class="px-2 py-0.5 bg-' + (levelColors[String(level)] || "gray") + "-100 text-" + (levelColors[String(level)] || "gray") + '-700 rounded text-xs">' + level + '</span></td><td class="py-2 px-2 text-xs">' + (catLabels[cat] || cat) + '</td><td class="py-2 px-2 font-mono text-xs max-w-32 truncate">' + escHtml$1(targetStr) + "</td></tr>";
    }).join("");
  }
  if (!window.reviewResults) {
    window.reviewResults = [];
  }
  function renderEngineStatus() {
    const el = document.getElementById("engine-status");
    if (!el) return;
    try {
      const text = document.getElementById("health-status")?.textContent || "{}";
      const health = JSON.parse(text);
      const specCount = window.SPEC_DATA?.length || 0;
      const [funcCount = "340", funcCap = "390"] = (health.engine?.func_registry || "340/390").split("/");
      el.innerHTML = `<div class="flex justify-between"><span>原子函数</span><span>${funcCount}/${funcCap} 已注册</span></div><div class="flex justify-between"><span>规范库</span><span>${specCount}条 (L1~L3)</span></div><div class="flex justify-between"><span>建筑类型阈值</span><span>civil/industrial</span></div><div class="flex justify-between"><span>判定过滤</span><span>实体类型匹配</span></div>`;
    } catch {
      el.innerHTML = `<div class="flex justify-between"><span>原子函数</span><span>340/390 已注册</span></div><div class="flex justify-between"><span>规范库</span><span>199条 (L1~L3)</span></div><div class="flex justify-between"><span>建筑类型阈值</span><span>civil/industrial</span></div><div class="flex justify-between"><span>判定过滤</span><span>实体类型匹配 (90.8%)</span></div>`;
    }
  }
  function resolveAction(name) {
    const parts = name.split(".");
    let cur = window;
    for (const p of parts) {
      if (!cur || typeof cur !== "object") return void 0;
      cur = cur[p];
    }
    return typeof cur === "function" ? cur : void 0;
  }
  let _delegatedBound = false;
  function bindActionDelegation() {
    if (_delegatedBound) return;
    _delegatedBound = true;
    document.addEventListener("click", (ev) => {
      const el = ev.target.closest("[data-action]");
      if (!el) return;
      const name = el.getAttribute("data-action");
      if (!name) return;
      let args = [];
      try {
        const raw = el.getAttribute("data-args") || "[]";
        args = JSON.parse(raw);
        args = args.map((a) => a === "@this@" ? ev.target : a);
      } catch {
        args = [];
      }
      const fn = resolveAction(name);
      if (!fn) {
        console.warn("[delegation] 未挂载的 action:", name, "on", el);
        return;
      }
      ev.preventDefault();
      try {
        const ret = fn(...args);
        if (ret && typeof ret.then === "function") {
          ret.catch((e) => console.error("[delegation] action error:", name, e));
        }
      } catch (e) {
        console.error("[delegation] action error:", name, e);
      }
    }, true);
  }
  function initApp() {
    appState.loadApiBase();
    initAdminToken();
    loadKeys();
    populateTokenSelect();
    loadParsedDrawings();
    renderDrawingList();
    refreshReviewDrawingSelect();
    loadReviewResults();
    loadDashboard();
    loadSpecs();
    const apiBase = document.getElementById("api-base");
    apiBase?.addEventListener("change", () => appState.saveApiBase());
    bindActionDelegation();
    renderEngineStatus();
  }
  const DEFAULT_STATUS_OPTIONS = [
    { value: "", label: "📋 全部" },
    { value: "unreviewed", label: "⚪ 未审核" },
    { value: "confirmed", label: "✅ 已确认" },
    { value: "dismissed", label: "❌ 已驳回" },
    { value: "pending", label: "⏳ 待核实" }
  ];
  const DEFAULT_SEVERITY_OPTIONS = [
    { value: "", label: "🚦 全部严重度" },
    { value: "critical", label: "🔴 严重" },
    { value: "major", label: "🟠 主要" },
    { value: "minor", label: "🟡 轻微" }
  ];
  function renderFilterBar(container, options = {}) {
    const statusOpts = options.statusOptions || DEFAULT_STATUS_OPTIONS;
    const severityOpts = options.severityOptions || DEFAULT_SEVERITY_OPTIONS;
    const clauseOpts = options.clauseOptions || [];
    const aStatus = options.activeStatus || "";
    const aSeverity = options.activeSeverity || "";
    const aClause = options.activeClause || "";
    const sel = "px-2 py-1 rounded text-xs bg-blue-100 text-blue-700 border border-blue-200";
    const unsel = "px-2 py-1 rounded text-xs bg-gray-100 text-gray-600 hover:bg-gray-200 border border-gray-200";
    let html = '<div class="flex flex-wrap items-center gap-2 mb-3 p-2 bg-gray-50 rounded-lg border"><span class="text-xs text-gray-500 font-medium">筛选:</span>';
    if (options.stats) {
      const s = options.stats;
      html += `<span class="text-xs text-gray-400 mr-2">|</span><span class="text-xs text-gray-500">已审核 <strong class="text-blue-600">${s.total - s.unreviewed}</strong>/${s.total} | 确认 <span class="text-green-600">${s.confirmed}</span> | 驳回 <span class="text-red-600">${s.dismissed}</span> | 待核实 <span class="text-yellow-600">${s.pending}</span></span>`;
    }
    if (statusOpts.length > 0) {
      html += '<span class="text-xs text-gray-400 ml-2">状态:</span>';
      for (const opt of statusOpts) {
        const cls = opt.value === aStatus ? sel : unsel;
        html += `<button data-filter-status="${opt.value}" class="${cls}">${opt.label}</button>`;
      }
    }
    if (severityOpts.length > 0) {
      html += '<span class="text-xs text-gray-400 ml-2">严重度:</span>';
      for (const opt of severityOpts) {
        const cls = opt.value === aSeverity ? sel : unsel;
        html += `<button data-filter-severity="${opt.value}" class="${cls}">${opt.label}</button>`;
      }
    }
    if (clauseOpts.length > 0) {
      html += '<span class="text-xs text-gray-400 ml-2">规范:</span>';
      for (const opt of clauseOpts.slice(0, 15)) {
        const cls = opt.value === aClause ? sel : unsel;
        html += `<button data-filter-clause="${opt.value}" class="${cls}">${opt.label}</button>`;
      }
      if (clauseOpts.length > 15) {
        html += `<span class="text-xs text-gray-400">+${clauseOpts.length - 15}</span>`;
      }
    }
    if (aStatus || aSeverity || aClause) {
      html += '<button data-filter-clear class="px-2 py-1 rounded text-xs bg-red-100 text-red-600 hover:bg-red-200 ml-auto">✕ 清除</button>';
    }
    html += "</div>";
    container.innerHTML = html;
    container.querySelectorAll("[data-filter-status]").forEach((btn) => {
      btn.addEventListener("click", () => {
        options.onChange?.(
          btn.dataset.filterStatus || "",
          aSeverity,
          aClause
        );
      });
    });
    container.querySelectorAll("[data-filter-severity]").forEach((btn) => {
      btn.addEventListener("click", () => {
        options.onChange?.(
          aStatus,
          btn.dataset.filterSeverity || "",
          aClause
        );
      });
    });
    container.querySelectorAll("[data-filter-clause]").forEach((btn) => {
      btn.addEventListener("click", () => {
        options.onChange?.(
          aStatus,
          aSeverity,
          btn.dataset.filterClause || ""
        );
      });
    });
    const clearBtn = container.querySelector("[data-filter-clear]");
    clearBtn?.addEventListener("click", () => {
      options.onChange?.("", "", "");
    });
  }
  if (typeof window !== "undefined") {
    window.renderFilterBar = renderFilterBar;
  }
  const SEV_COLOR = {
    critical: "red",
    major: "orange",
    minor: "yellow"
  };
  const SEV_LABEL = {
    critical: "严重",
    major: "主要",
    minor: "轻微"
  };
  function confColor(conf) {
    if (conf >= 0.85) return "green";
    if (conf >= 0.6) return "yellow";
    return "red";
  }
  function confLabel(conf) {
    if (conf >= 0.85) return "高";
    if (conf >= 0.6) return "中";
    return "低";
  }
  function renderReviewItem(props) {
    const sevColor = SEV_COLOR[props.severity] || "orange";
    const sevLabel = SEV_LABEL[props.severity] || props.severity;
    const conf = Math.max(0, Math.min(1, props.confidence));
    const confPct = Math.round(conf * 100);
    const cColor = confColor(conf);
    const cLabel = confLabel(conf);
    let html = '<div class="p-2 bg-' + sevColor + '-50 rounded text-xs mb-1.5"><div class="flex justify-between items-start"><div><span class="font-medium">' + escHtml$1(props.clauseTitle) + '</span> <span class="text-gray-400">(' + escHtml$1(props.funcId || props.clauseId) + ')</span></div><div class="flex gap-1"><span class="px-1.5 py-0.5 rounded text-xs font-medium bg-' + sevColor + "-100 text-" + sevColor + '-700">' + sevLabel + '</span><span class="px-1.5 py-0.5 rounded text-xs font-medium bg-' + cColor + "-100 text-" + cColor + '-700" title="置信度 ' + confPct + '%">' + cLabel + '</span><span class="text-' + sevColor + '-600 font-medium">' + escHtml$1(props.result) + '</span></div></div><span class="text-gray-500">' + escHtml$1(props.entityType) + " · 实测: " + (props.extractedValue != null ? props.extractedValue.toFixed(2) : "-") + " · 要求: " + (props.requiredValue != null ? props.requiredValue.toFixed(2) : "-") + '</span><br/><div class="mt-1"><div class="w-full bg-gray-200 rounded-full h-1"><div class="' + cColor + '-500 h-1 rounded-full" style="width:' + confPct + '%"></div></div></div><span class="text-gray-400">' + escHtml$1(props.explanation) + "</span>";
    if (props.corrections && props.corrections.length > 0) {
      const top = props.corrections[0];
      const pColor = top.priority === "high" ? "red" : top.priority === "medium" ? "orange" : "yellow";
      const pLabel = top.priority === "high" ? "🔴 高" : top.priority === "medium" ? "🟠 中" : "🟡 低";
      html += '<details class="mt-1"><summary class="cursor-pointer text-purple-600 font-medium">💡 修正建议 (' + props.corrections.length + '条)</summary><div class="mt-0.5 p-1 bg-' + pColor + "-50 rounded border-l-2 border-" + pColor + '-400"><p class="text-xs"><span class="text-' + pColor + '-600">' + pLabel + "</span> " + escHtml$1(top.recommendation) + "</p>" + (Object.keys(top.parameters || {}).length > 0 ? '<p class="text-xs text-gray-400 mt-0.5">参数: ' + JSON.stringify(top.parameters) + "</p>" : "") + "</div></details>";
    }
    if (props.auditItemId) {
      html += renderAuditButtons$1(props.auditItemId, props.auditState || "unreviewed", props.clauseId);
    }
    html += "</div>";
    return html;
  }
  function renderAuditButtons$1(itemId, itemStatus, clauseId) {
    const safeClause = escHtml$1(clauseId || "");
    let html = '<div class="flex gap-1 mt-1"><span class="text-[10px] text-gray-400">审核:</span>';
    switch (itemStatus) {
      case "confirmed":
        html += `<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">✅ 已确认</span><button onclick="auditAction('` + escHtml$1(itemId) + "','dismiss','" + safeClause + `')" class="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600 hover:bg-red-100 hover:text-red-700">↩ 驳回</button>`;
        break;
      case "dismissed":
        html += `<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">❌ 已驳回</span><button onclick="auditAction('` + escHtml$1(itemId) + "','confirm','" + safeClause + `')" class="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600 hover:bg-green-100 hover:text-green-700">↩ 确认</button>`;
        break;
      case "pending":
        html += `<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-700">⏳ 待核实</span><button onclick="auditAction('` + escHtml$1(itemId) + "','confirm','" + safeClause + `')" class="px-1.5 py-0.5 rounded text-xs bg-green-100 text-green-700 hover:bg-green-200">✅ 确认</button><button onclick="auditAction('` + escHtml$1(itemId) + "','dismiss','" + safeClause + `')" class="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-700 hover:bg-red-200">❌ 驳回</button>`;
        break;
      default:
        html += `<button onclick="auditAction('` + escHtml$1(itemId) + "','confirm','" + safeClause + `')" class="px-1.5 py-0.5 rounded text-xs bg-green-100 text-green-700 hover:bg-green-200">✅ 确认</button><button onclick="auditAction('` + escHtml$1(itemId) + "','dismiss','" + safeClause + `')" class="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-700 hover:bg-red-200">❌ 驳回</button><button onclick="auditAction('` + escHtml$1(itemId) + "','pending','" + safeClause + `')" class="px-1.5 py-0.5 rounded text-xs bg-yellow-100 text-yellow-700 hover:bg-yellow-200">⏳ 待核实</button>`;
    }
    html += "</div>";
    return html;
  }
  if (typeof window !== "undefined") {
    window.renderReviewItem = renderReviewItem;
  }
  function renderReviewTable(container, options) {
    const { items, page: curPage = 1, pageSize = 20 } = options;
    const filtered = filterItems(items, options);
    const total = filtered.length;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const page = Math.max(1, Math.min(curPage, totalPages));
    const start = (page - 1) * pageSize;
    const end = Math.min(start + pageSize, total);
    const pageItems = filtered.slice(start, end);
    if (total === 0) {
      container.innerHTML = '<div class="text-center py-8 text-gray-400 text-sm">暂无违规数据</div>';
      return;
    }
    let html = "";
    for (const item of pageItems) {
      html += renderReviewItem(item);
    }
    if (totalPages > 1) {
      html += '<div class="flex items-center justify-center gap-2 mt-3 text-xs">';
      html += '<button data-page="prev" class="px-2 py-1 border rounded hover:bg-gray-100"' + (page <= 1 ? " disabled" : "") + ">‹</button>";
      const pageRangeStart = Math.max(1, page - 2);
      const pageRangeEnd = Math.min(totalPages, page + 2);
      for (let p = pageRangeStart; p <= pageRangeEnd; p++) {
        html += '<button data-page="' + p + '" class="px-2 py-1 border rounded ' + (p === page ? "bg-blue-100 text-blue-700" : "hover:bg-gray-100") + '">' + p + "</button>";
      }
      html += '<button data-page="next" class="px-2 py-1 border rounded hover:bg-gray-100"' + (page >= totalPages ? " disabled" : "") + ">›</button>";
      html += '<span class="text-gray-400">' + page + "/" + totalPages + "</span>";
      html += "</div>";
    }
    html += `<div class="text-xs text-gray-400 text-right mt-1">共 ${total} 条违规</div>`;
    container.innerHTML = html;
    container.querySelectorAll("[data-page]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const val = btn.dataset.page;
        if (!val || val === "prev" || val === "next") return;
        if (typeof window !== "undefined") {
          const w2 = window;
          if (typeof w2.renderViolationPage === "function") {
            w2["_reviewPage"] = parseInt(val, 10);
            w2.renderViolationPage();
          }
        }
      });
    });
  }
  function filterItems(items, options) {
    let filtered = items;
    if (options.filterStatus) {
      filtered = filtered.filter((i) => i.auditState === options.filterStatus);
    }
    if (options.filterSeverity) {
      filtered = filtered.filter((i) => i.severity === options.filterSeverity);
    }
    return filtered;
  }
  if (typeof window !== "undefined") {
    window.renderReviewTable = renderReviewTable;
  }
  function _escHtml(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  async function _initAuditItems(result) {
    const reviewId = result.queue_info?.task_id || result.task_id || "";
    if (!reviewId) return;
    const details = (result.findings || []).filter((f) => f.result === "FAIL" && !f.is_duplicate);
    if (details.length === 0) {
      window._reviewAuditMapping = {};
      return;
    }
    try {
      const url = window.API_BASE?.() + "/api/v1/audit/items";
      const r = await fetch(url, {
        method: "POST",
        headers: { ...window.HEADERS?.() || {}, "Content-Type": "application/json" },
        body: JSON.stringify({ review_id: reviewId, details })
      });
      if (r.ok) {
        const mapping = {};
        details.forEach((d, i) => {
          const fid = d.func_id || d.clause_id || "";
          const eid = d.entity_id || "";
          mapping[fid + ":" + eid + ":" + i] = reviewId + ":" + i;
        });
        window._reviewAuditMapping = { mapping, reviewId };
        window._reviewAuditDetailList = details;
        await _loadAuditItemStates(reviewId);
      }
    } catch (err) {
      console.warn("[P119] 审计条目初始化失败:", err.message);
    }
  }
  async function _loadAuditItemStates(reviewId) {
    try {
      const url = window.API_BASE?.() + "/api/v1/audit/items?review_id=" + encodeURIComponent(reviewId);
      const r = await fetch(url, { headers: window.HEADERS?.() || {} });
      if (r.ok) {
        const resp = await r.json();
        const states = {};
        (resp.items || []).forEach((item) => {
          states[item.id] = item.status;
        });
        window._reviewAuditStates = states;
      }
    } catch (err) {
      console.warn("[P119] 审计状态加载失败:", err.message);
    }
  }
  function renderAuditButtons(itemId, itemStatus, clauseId) {
    if (!itemId) return "";
    const safeClause = _escHtml(clauseId || "");
    let html = '<div class="flex gap-1 mt-1"><span class="text-[10px] text-gray-400">审核:</span>';
    switch (itemStatus) {
      case "confirmed":
        html += '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">✅ 已确认</span>';
        html += `<button onclick="window.auditAction('` + itemId + "','dismiss','" + safeClause + `')" class="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600 hover:bg-red-100 hover:text-red-700">↩ 驳回</button>`;
        break;
      case "dismissed":
        html += '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">❌ 已驳回</span>';
        html += `<button onclick="window.auditAction('` + itemId + "','confirm','" + safeClause + `')" class="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600 hover:bg-green-100 hover:text-green-700">↩ 确认</button>`;
        break;
      case "pending":
        html += '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-700">⏳ 待核实</span>';
        html += `<button onclick="window.auditAction('` + itemId + "','confirm','" + safeClause + `')" class="px-1.5 py-0.5 rounded text-xs bg-green-100 text-green-700 hover:bg-green-200">✅ 确认</button>`;
        html += `<button onclick="window.auditAction('` + itemId + "','dismiss','" + safeClause + `')" class="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-700 hover:bg-red-200">❌ 驳回</button>`;
        break;
      default:
        html += `<button onclick="window.auditAction('` + itemId + "','confirm','" + safeClause + `')" class="px-1.5 py-0.5 rounded text-xs bg-green-100 text-green-700 hover:bg-green-200">✅ 确认</button>`;
        html += `<button onclick="window.auditAction('` + itemId + "','dismiss','" + safeClause + `')" class="px-1.5 py-0.5 rounded text-xs bg-red-100 text-red-700 hover:bg-red-200">❌ 驳回</button>`;
        html += `<button onclick="window.auditAction('` + itemId + "','pending','" + safeClause + `')" class="px-1.5 py-0.5 rounded text-xs bg-yellow-100 text-yellow-700 hover:bg-yellow-200">⏳ 待核实</button>`;
    }
    html += "</div>";
    return html;
  }
  async function auditAction(itemId, action, clauseId) {
    const safeAction = _escHtml(action || "");
    try {
      const body = action === "dismiss" ? { reason: "人工驳回" } : {};
      const url = window.API_BASE?.() + "/api/v1/audit/items/" + encodeURIComponent(itemId) + "/" + safeAction;
      const r = await fetch(url, {
        method: "POST",
        headers: { ...window.HEADERS?.() || {}, "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      if (!r.ok) {
        const err = await r.json();
        showToast?.("操作失败: " + (err.detail || r.statusText), "error");
        return;
      }
      showToast?.(
        (action === "confirm" ? "✅ 已确认违规" : action === "dismiss" ? "❌ 已驳回（误报）" : "⏳ 已标记待核实") + " " + _escHtml(clauseId || ""),
        "info"
      );
      renderViolationPage?.();
    } catch (err) {
      showToast?.("网络错误: " + err.message, "error");
    }
  }
  const STATUS_META = {
    all: { label: "全部", color: "bg-gray-100 text-gray-700" },
    unreviewed: { label: "未审核", color: "bg-gray-200 text-gray-800" },
    confirmed: { label: "已确认", color: "bg-green-100 text-green-700" },
    dismissed: { label: "已驳回", color: "bg-red-100 text-red-700" },
    pending: { label: "待核实", color: "bg-yellow-100 text-yellow-700" }
  };
  function renderAuditStatsBar(reviewId, stats) {
    const safeId = _escHtml(reviewId);
    const { total, confirmed, dismissed, pending, unreviewed } = stats;
    let html = '<div id="audit-stats-bar" class="mb-3 bg-blue-50 border border-blue-200 rounded-lg px-4 py-2.5 flex items-center gap-4 flex-wrap">';
    html += '<span class="text-xs font-semibold text-blue-800 mr-2">📋 审核进度</span>';
    const reviewed = confirmed + dismissed + pending;
    html += '<span class="text-xs text-blue-600">已审核 <b>' + reviewed + "</b> / <b>" + total + "</b></span>";
    if (unreviewed > 0) html += _statChip("⏳ " + unreviewed + " 未审核", "bg-gray-200 text-gray-800");
    if (confirmed > 0) html += _statChip("✅ " + confirmed + " 确认", "bg-green-100 text-green-700");
    if (dismissed > 0) html += _statChip("❌ " + dismissed + " 驳回", "bg-red-100 text-red-700");
    if (pending > 0) html += _statChip("⏳ " + pending + " 待核实", "bg-yellow-100 text-yellow-700");
    if (total === 0) html += '<span class="text-xs text-gray-500">暂无审核条目</span>';
    html += "</div>";
    html += '<div id="audit-filter-bar" class="mb-3 flex items-center gap-2">';
    html += `<select id="audit-status-filter" onchange="window._onAuditFilterChange(this.value,'` + safeId + `')" class="text-xs border rounded px-2 py-1">`;
    ["all", "unreviewed", "confirmed", "dismissed", "pending"].forEach((k) => {
      const m = STATUS_META[k];
      html += '<option value="' + k + '">' + m.label + "</option>";
    });
    html += "</select>";
    if (confirmed > 0) {
      html += `<button onclick="window.downloadCorrectionNotice('` + safeId + `')" class="ml-auto px-3 py-1 bg-red-600 text-white text-xs rounded hover:bg-red-700">📄 生成整改通知单</button>`;
    }
    html += "</div>";
    return html;
  }
  function _statChip(text, css) {
    return '<span class="px-2 py-0.5 rounded text-xs font-medium ' + css + '">' + text + "</span>";
  }
  async function _loadAuditStats(reviewId) {
    try {
      const url = window.API_BASE?.() + "/api/v1/audit/stats?review_id=" + encodeURIComponent(reviewId);
      const r = await fetch(url, { headers: window.HEADERS?.() || {} });
      if (r.ok) {
        const resp = await r.json();
        window._auditStats = resp.stats;
        return resp.stats;
      }
    } catch (err) {
      console.warn("[P119] 审核统计加载失败:", err.message);
    }
    return null;
  }
  async function _refreshAuditPanel(reviewId) {
    const stats = await _loadAuditStats(reviewId);
    if (!stats) return;
    const barEl = document.getElementById("audit-stats-bar");
    if (barEl) {
      barEl.outerHTML = renderAuditStatsBar(reviewId, stats);
    }
    await _loadAuditItemStates(reviewId);
    renderViolationPage?.();
  }
  async function _onAuditFilterChange(status, reviewId) {
    window._auditFilterStatus = status === "all" ? "" : status;
    renderViolationPage?.();
  }
  async function downloadCorrectionNotice(reviewId) {
    try {
      const url = window.API_BASE?.() + "/api/v1/audit/export/pdf?review_id=" + encodeURIComponent(reviewId);
      const r = await fetch(url, { headers: window.HEADERS?.() || {} });
      if (!r.ok) {
        showToast?.("生成失败: " + r.statusText, "error");
        return;
      }
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "correction-notice-" + _escHtml(reviewId) + ".pdf";
      a.click();
      URL.revokeObjectURL(a.href);
      showToast?.("✅ 整改通知单已下载", "info");
    } catch (err) {
      showToast?.("网络错误: " + err.message, "error");
    }
  }
  async function runReview() {
    const select = document.getElementById("review-drawing-select");
    const id = select?.value ?? "";
    if (!id) {
      window.showToast?.("请选择已解析的图纸", "info");
      return;
    }
    const drawings = getParsedDrawings();
    const drawing = drawings.find((d) => d.id === id);
    if (!drawing) {
      window.showToast?.("图纸数据不存在", "info");
      return;
    }
    const bt = drawing.building_type || "";
    const entities = drawing.entities || drawing.raw?.entities || [];
    if (entities.length === 0) {
      window.showToast?.("该图纸没有解析出实体数据，请重新上传解析", "info");
      return;
    }
    const loading = document.getElementById("review-loading");
    if (loading) {
      loading.classList.remove("hidden");
      loading.textContent = "⏳ 正在审查...";
    }
    const btn = document.getElementById("review-start-btn");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "⏳ 审查中...";
    }
    try {
      const url = window.API_BASE?.() + "/review-from-data";
      const r = await fetch(url, {
        method: "POST",
        headers: { ...window.HEADERS?.() || {}, "Content-Type": "application/json" },
        body: JSON.stringify({ entities, building_type: bt })
      });
      const result = await r.json();
      if (loading) loading.classList.add("hidden");
      if (btn) {
        btn.disabled = false;
        btn.textContent = "🔍 开始审查";
      }
      const summary = document.getElementById("review-summary");
      const details = document.getElementById("review-details");
      window._currentReviewResult = result;
      window._currentReviewEntities = entities;
      if (result.status === "success") {
        renderReviewSummary(summary, result);
        renderReviewDetails(details, result);
        _initAuditItems(result).then(() => {
          const reviewId = result.queue_info?.task_id || result.task_id || "";
          if (reviewId) {
            _refreshAuditPanel(reviewId);
          }
        });
      } else {
        if (summary) {
          summary.innerHTML = '<span class="text-red-500">❌ 审查失败: ' + (result.message || "未知错误") + "</span>";
        }
      }
    } catch (err) {
      if (loading) loading.classList.add("hidden");
      if (btn) {
        btn.disabled = false;
        btn.textContent = "🔍 开始审查";
      }
      const msg = err instanceof Error ? err.message : String(err);
      const summary = document.getElementById("review-summary");
      if (summary) {
        summary.innerHTML = '<span class="text-red-500">❌ 审查失败: ' + msg + "</span>";
      }
    }
  }
  function renderReviewSummary(container, result) {
    if (!container) return;
    const vs = result.summary || {};
    const tc = vs.confidence_tier_counts || { confirmed: 0, suspected: 0, needs_review: 0 };
    let html = '<div class="grid grid-cols-4 gap-2 mb-3"><div class="card p-2 text-center"><div class="text-lg font-bold text-blue-600">' + (vs.violations || 0) + '</div><div class="text-xs text-gray-400">违规</div></div><div class="card p-2 text-center"><div class="text-lg font-bold text-red-600">' + (tc.confirmed || 0) + '</div><div class="text-xs text-gray-400">✅ 确认违规</div></div><div class="card p-2 text-center"><div class="text-lg font-bold text-yellow-600">' + (tc.suspected || 0) + '</div><div class="text-xs text-gray-400">🟡 疑似违规</div></div><div class="card p-2 text-center"><div class="text-lg font-bold text-orange-600">' + (tc.needs_review || 0) + '</div><div class="text-xs text-gray-400">🔴 建议复核</div></div></div>';
    const reviewId = result.queue_info?.task_id || result.task_id || "";
    const summaryObj = result.summary || {};
    const entityTypes = summaryObj.entity_types || {};
    if (Object.keys(entityTypes).length > 0 || reviewId) {
      const extras = [];
      if (Object.keys(entityTypes).length > 0) {
        const parts = [];
        for (const [type, count] of Object.entries(entityTypes)) {
          parts.push('<span class="px-2 py-0.5 bg-gray-100 rounded text-xs">' + type + ": " + count + "</span>");
        }
        extras.push('<p class="text-xs text-gray-400 mb-2">构件分布:</p><div class="flex flex-wrap gap-1 mb-3">' + parts.join("") + "</div>");
      }
      if (reviewId) {
        const safeId = window._escHtml?.(reviewId) || reviewId;
        extras.push(
          `<div class="mt-3 flex gap-2 flex-wrap"><button onclick="window.downloadReviewPdf?.('` + safeId + `')" class="px-3 py-1.5 bg-red-600 text-white text-xs rounded-lg hover:bg-red-700">📄 PDF报告</button><button onclick="window.downloadReviewExport?.('` + safeId + `','json')" class="px-3 py-1.5 bg-green-600 text-white text-xs rounded-lg hover:bg-green-700">📋 导出JSON</button><button onclick="window.downloadReviewExport?.('` + safeId + `','csv')" class="px-3 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700">📊 导出CSV</button></div>`
        );
      }
      html += extras.join("");
    }
    container.innerHTML = html;
  }
  function renderReviewDetails(container, result) {
    if (!container) return;
    const findings = result.findings || [];
    const violations = findings.filter((f) => f.result === "FAIL" && !f.is_duplicate);
    if (violations.length === 0) {
      container.innerHTML = '<div class="text-center py-8 text-green-400 text-sm">✅ 无违规，图纸合规</div>';
      return;
    }
    const sevCounts = {};
    violations.forEach((f) => {
      const sev = f.severity || "major";
      sevCounts[sev] = (sevCounts[sev] || 0) + 1;
    });
    const totalViols = Object.values(sevCounts).reduce((a, b) => a + b, 0);
    let html = "";
    if (totalViols > 0) {
      const sevColors = { critical: "bg-red-500", major: "bg-orange-500", minor: "bg-yellow-400" };
      const sevLabels = { critical: "严重", major: "主要", minor: "轻微" };
      const sevTextColors = { critical: "text-red-700", major: "text-orange-700", minor: "text-yellow-700" };
      const sevGrid = ["critical", "major", "minor"].map((sev) => {
        const count = sevCounts[sev] || 0;
        const pct = totalViols > 0 ? (count / totalViols * 100).toFixed(0) : 0;
        return '<div class="card p-2 text-center"><div class="text-lg font-bold ' + (sevTextColors[sev] || "text-gray-600") + '">' + count + '</div><div class="text-xs text-gray-400">' + (sevLabels[sev] || sev) + '</div><div class="w-full bg-gray-100 rounded-full h-1.5 mt-1"><div class="' + (sevColors[sev] || "bg-gray-400") + ' h-1.5 rounded-full" style="width:' + pct + '%"></div></div></div>';
      });
      html += '<div class="grid grid-cols-3 gap-2 mb-3">' + sevGrid.join("") + "</div>";
    }
    html += '<div id="audit-stats-bar-container"></div>';
    html += '<div id="review-table-container"></div>';
    container.innerHTML = html;
    const tableContainer = document.getElementById("review-table-container");
    if (tableContainer) {
      const items = violations.map((f) => mapFindingToItem(f));
      renderReviewTable(tableContainer, { items });
    }
  }
  function mapFindingToItem(f) {
    const corrKey = (f.clause_id || f.func_id || "").trim();
    const corrections = window._currentReviewResult?.corrections || [];
    const matchingCorrections = corrections.filter((c) => c.clause_id === corrKey);
    let auditItemId;
    let auditState;
    const mapping = window._reviewAuditMapping;
    if (mapping?.mapping) {
      const fid = f.func_id || f.clause_id || "";
      const eid = f.entity_id || "";
      const key = fid + ":" + eid;
      if (mapping.mapping[key]) {
        auditItemId = mapping.mapping[key];
        const states = window._reviewAuditStates;
        auditState = states?.[auditItemId] || "unreviewed";
      }
    }
    return {
      funcId: f.func_id || "",
      clauseId: f.clause_id || "",
      clauseTitle: f.clause_title || "",
      severity: f.severity || "major",
      confidence: f.confidence != null ? f.confidence : 1,
      confidenceTier: f.confidence_tier || void 0,
      entityType: f.entity_type || "",
      extractedValue: f.extracted_value != null ? f.extracted_value : null,
      requiredValue: f.required_value != null ? f.required_value : null,
      explanation: f.explanation || "",
      result: f.result || "",
      entityId: f.entity_id || "",
      corrections: matchingCorrections.map((c) => ({
        recommendation: c.recommendation || "",
        priority: c.priority || "medium",
        parameters: c.parameters || {}
      })),
      auditItemId,
      auditState: auditState || "unreviewed"
    };
  }
  const ENTITY_COLORS = {
    staircase: "#ef4444",
    stair: "#ef4444",
    corridor: "#f97316",
    aisle: "#f97316",
    fire_door: "#ef4444",
    door: "#f59e0b",
    fire_lane: "#ef4444",
    road: "#ef4444",
    fire_zone: "#f97316",
    room: "#22c55e",
    exit: "#ef4444",
    exit_door: "#ef4444",
    fire_window: "#f97316",
    window: "#3b82f6",
    refuge_floor: "#ef4444",
    exit_sign: "#f59e0b",
    sign: "#f59e0b",
    sprinkler_system: "#f97316",
    fire_alarm: "#f97316",
    shaft: "#f59e0b",
    insulation: "#f97316",
    evacuation_lighting: "#f59e0b",
    wall: "#6b7280"
  };
  function renderViolationOverlay(canvas, result, emptyElId) {
    const viols = result.details || [];
    const elements = result.elements || result.rawResult?.elements || [];
    const hasPosData = elements.length > 0 || viols.some((v) => v.entity_type);
    if (!hasPosData) {
      if (emptyElId) {
        const el = document.getElementById(emptyElId);
        if (el) {
          el.className = "absolute inset-0 flex items-center justify-center text-gray-400 text-sm";
          el.textContent = "无实体位置数据";
        }
      }
      canvas.style.display = "none";
      return;
    }
    if (emptyElId) {
      const emptyEl = document.getElementById(emptyElId);
      if (emptyEl) emptyEl.className = "hidden";
    }
    canvas.style.display = "block";
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#f8f9fa";
    ctx.fillRect(0, 0, W, H);
    const violTypes = {};
    const violClauses = {};
    viols.forEach((v) => {
      const et = v.entity_type || "unknown";
      const severity = v.severity || "major";
      if (!violTypes[et] || violTypes[et] === "major") violTypes[et] = severity;
      if (!violClauses[et]) violClauses[et] = [];
      violClauses[et].push(v.clause_id + ": " + (v.clause_title || ""));
    });
    const allTypes = [
      ...new Set([
        ...viols.map((v) => v.entity_type || "unknown"),
        ...elements.map((e) => e.type || e.entity_type || "")
      ].filter(Boolean))
    ];
    if (allTypes.length === 0) {
      ctx.fillStyle = "#999";
      ctx.font = "14px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("无实体位置数据", W / 2, H / 2);
      return;
    }
    const cols = Math.min(4, Math.ceil(Math.sqrt(allTypes.length)));
    const rows = Math.ceil(allTypes.length / cols);
    const cellW = (W - 60) / cols;
    const cellH = (H - 60) / rows;
    const circles = [];
    allTypes.forEach((t, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const cx = 30 + col * cellW + cellW / 2;
      const cy = 30 + row * cellH + cellH / 2;
      const radius = Math.min(cellW, cellH) * 0.3;
      const color = ENTITY_COLORS[t] || "#6b7280";
      const severity = violTypes[t] || "none";
      const isViolated = violTypes[t] !== void 0;
      const hints = violClauses[t] || [];
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
      ctx.fillStyle = isViolated ? severity === "critical" ? "#fecaca" : "#fed7aa" : "#dcfce7";
      ctx.fill();
      ctx.strokeStyle = color;
      ctx.lineWidth = isViolated ? 3 : 1.5;
      ctx.stroke();
      ctx.fillStyle = color;
      ctx.font = "bold 10px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      const label = t.length > 12 ? t.slice(0, 10) + ".." : t;
      ctx.fillText(label, cx, cy);
      if (isViolated) {
        ctx.fillStyle = color;
        ctx.font = "bold 8px sans-serif";
        ctx.fillText("✗", cx + radius + 8, cy - radius);
      }
      if (hints.length > 0) {
        ctx.fillStyle = "#6b7280";
        ctx.font = "7px sans-serif";
        ctx.textAlign = "center";
        hints.slice(0, 2).forEach((h, hi) => {
          ctx.fillText(
            h.length > 20 ? h.slice(0, 18) + ".." : h,
            cx,
            cy + 12 + hi * 10
          );
        });
      }
      circles.push({ x: cx, y: cy, r: radius, type: t, color, severity, isViolated, hints });
    });
    let tip = document.getElementById("compare-vis-tooltip");
    if (!tip) {
      tip = document.createElement("div");
      tip.id = "compare-vis-tooltip";
      tip.className = "fixed hidden bg-black bg-opacity-90 text-white text-xs rounded-lg p-2 pointer-events-none z-50 max-w-xs shadow-lg";
      document.body.appendChild(tip);
    }
    if (canvas.__onMove) {
      canvas.removeEventListener(
        "mousemove",
        canvas.__onMove
      );
    }
    if (canvas.__onLeave) {
      canvas.removeEventListener(
        "mouseleave",
        canvas.__onLeave
      );
    }
    canvas.__circles = circles;
    canvas.__tooltip = tip;
    const onMove = (e) => {
      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;
      const mx = (e.clientX - rect.left) * scaleX;
      const my = (e.clientY - rect.top) * scaleY;
      let hit = null;
      let hitDist = Infinity;
      for (const c of circles) {
        const d = Math.hypot(mx - c.x, my - c.y);
        if (d < c.r * 1.3 && d < hitDist) {
          hit = c;
          hitDist = d;
        }
      }
      if (!hit) {
        tip.classList.add("hidden");
        return;
      }
      const sevText = hit.severity === "critical" ? "严重" : hit.severity === "major" ? "主要" : "轻微";
      const sevColor = hit.severity === "critical" ? "red" : hit.severity === "major" ? "orange" : "yellow";
      let html = '<div class="font-medium mb-1">' + hit.type + (hit.isViolated ? " ✗" : " ✓") + "</div>";
      if (hit.isViolated) {
        html += '<div class="mb-1"><span class="text-' + sevColor + '-400">● ' + sevText + "</span></div>";
        if (hit.hints.length > 0) {
          html += '<div class="text-gray-300 text-[10px]">' + hit.hints.slice(0, 4).join("<br>") + "</div>";
          if (hit.hints.length > 4) {
            html += '<div class="text-gray-500 text-[10px]">… 还有 ' + (hit.hints.length - 4) + " 条</div>";
          }
        }
      } else {
        html += '<div class="text-gray-400 text-[10px]">无违规</div>';
      }
      tip.innerHTML = html;
      tip.style.left = e.clientX + 12 + "px";
      tip.style.top = e.clientY + 12 + "px";
      tip.classList.remove("hidden");
    };
    const onLeave = () => {
      tip.classList.add("hidden");
    };
    canvas.__onMove = onMove;
    canvas.__onLeave = onLeave;
    canvas.addEventListener("mousemove", onMove);
    canvas.addEventListener("mouseleave", onLeave);
  }
  if (typeof window !== "undefined") {
    window.renderViolationOverlay = renderViolationOverlay;
  }
  const DEFAULT_IDS = {
    summary: "batch-review-summary",
    details: "batch-review-details",
    loading: "batch-review-loading",
    btn: "batch-review-start-btn"
  };
  function getEl(id) {
    return document.getElementById(id);
  }
  async function runBatchReview(files, options = {}) {
    if (files.length === 0) {
      showToast$1("请先选择至少一个图纸文件", "info");
      return;
    }
    const ids = { ...DEFAULT_IDS, ...options };
    const btn = getEl(ids.btn);
    const loading = getEl(ids.loading);
    const summary = getEl(ids.summary);
    const details = getEl(ids.details);
    btn?.setAttribute("disabled", "true");
    loading?.classList.remove("hidden");
    loading.textContent = "⏳ 正在批量审查...";
    if (summary) summary.innerHTML = "";
    if (details) details.innerHTML = "";
    const formData = new FormData();
    files.forEach((f) => formData.append("files", f));
    try {
      const r = await fetch(getApiBase() + "/batch-review", {
        method: "POST",
        headers: getHeaders(),
        body: formData
      });
      const resp = await r.json();
      if (!r.ok) {
        throw new Error(resp.detail?.message || "审查请求失败");
      }
      if (resp.status !== "success") {
        throw new Error(resp.message || "审查失败");
      }
      renderBatchSummary(resp.batch_summary, summary);
      renderBatchDetails(resp, details);
      if (loading) loading.classList.add("hidden");
    } catch (err) {
      if (loading) {
        loading.textContent = "❌ " + err.message;
        loading.className = "mt-3 text-sm text-red-500";
      }
    } finally {
      btn?.removeAttribute("disabled");
    }
  }
  function renderBatchSummary(bs, summary) {
    if (!summary) return;
    const timeSec = (bs.processing_time_ms / 1e3).toFixed(1);
    summary.innerHTML = '<div class="grid grid-cols-2 gap-2 mb-2"><div class="card p-2 text-xs"><p class="font-medium">📁 文件统计</p><p>总数: ' + bs.total_files + " | ✅成功: " + bs.success_files + " | ❌失败: " + bs.failed_files + '</p></div><div class="card p-2 text-xs"><p class="font-medium">📊 审查统计</p><p>实体: ' + bs.total_entities + " | 检查: " + bs.total_checks.toLocaleString() + " | 违规: " + bs.total_violations + "</p><p>耗时: " + timeSec + "s</p></div></div>";
  }
  function renderBatchDetails(resp, details) {
    if (!details) return;
    let crossHtml = "";
    if (resp.cross_analysis && resp.cross_analysis.length > 0) {
      crossHtml = '<div class="card p-2 text-xs mb-2"><p class="font-medium text-sm mb-1">🔗 跨文件违规交叉分析</p><table class="w-full text-xs"><thead><tr class="text-left text-gray-400 border-b"><th class="pb-1 pr-1">规范条款</th><th class="pb-1 pr-1">违规数</th><th class="pb-1 pr-1">涉及图纸</th><th class="pb-1 pr-1">文件</th></tr></thead><tbody>';
      resp.cross_analysis.slice(0, 8).forEach((c) => {
        crossHtml += '<tr class="border-b border-gray-50"><td class="py-1 pr-1">' + escHtml$1(c.clause_id) + '</td><td class="py-1 pr-1">' + c.violations + '</td><td class="py-1 pr-1">' + c.files + ' 张</td><td class="py-1 text-gray-400 truncate max-w-20">' + escHtml$1((c.file_names || []).join(", ")) + "</td></tr>";
      });
      crossHtml += "</tbody></table></div>";
    }
    let fileHtml = '<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">';
    resp.results.forEach((r) => {
      if (r.status === "error") {
        fileHtml += '<div class="card p-2 text-xs border-l-2 border-red-500 bg-red-50"><p class="font-medium text-red-600">❌ ' + escHtml$1(r.filename || "") + '</p><p class="text-gray-500">' + escHtml$1(r.message || "") + "</p></div>";
        return;
      }
      const s = r.summary || {};
      const isClean = (s.violations || 0) === 0;
      const sevColor = isClean ? "green" : (s.violations || 0) >= 20 ? "red" : "orange";
      const total = s.total_checks || 0;
      const passRate = total > 0 ? Math.round((1 - (s.violations || 0) / total) * 100) : 100;
      const sevCount = { critical: 0, major: 0, minor: 0 };
      (r.details || []).forEach((v) => {
        const sv = String(v.severity || "major");
        if (sv in sevCount) sevCount[sv]++;
      });
      const bar = '<div class="mt-1 bg-gray-200 rounded-full h-1.5 overflow-hidden"><div class="' + sevColor + '-500 h-full rounded-full" style="width:' + passRate + '%"></div></div><div class="flex justify-between text-[10px] text-gray-400 mt-0.5"><span>通过率 ' + passRate + "%</span><span>检查 " + total.toLocaleString() + "</span></div>";
      let badges = "";
      if (sevCount.critical > 0)
        badges += '<span class="px-1 rounded bg-red-100 text-red-700 text-[10px]">● ' + sevCount.critical + " 严重</span>";
      if (sevCount.major > 0)
        badges += '<span class="px-1 rounded bg-orange-100 text-orange-700 text-[10px]">● ' + sevCount.major + " 主要</span>";
      if (sevCount.minor > 0)
        badges += '<span class="px-1 rounded bg-yellow-100 text-yellow-700 text-[10px]">● ' + sevCount.minor + " 轻微</span>";
      if (!badges)
        badges = '<span class="px-1 rounded bg-green-100 text-green-700 text-[10px]">✓ 无违规</span>';
      const violByClause = s.violation_by_clause || {};
      const topClauses = Object.entries(violByClause).slice(0, 3);
      const clauseText = topClauses.length > 0 ? '<p class="text-[10px] text-gray-400 mt-1">主要: ' + topClauses.map(([k, v]) => k + "(" + v + ")").join(", ") + "</p>" : "";
      fileHtml += '<div class="card p-2 text-xs border-l-2 border-' + sevColor + '-500"><div class="flex items-center justify-between mb-1"><p class="font-medium truncate" title="' + escHtml$1(r.filename || "") + '">' + escHtml$1(r.filename || "") + '</p><span class="text-' + sevColor + '-600 font-medium text-sm">' + (isClean ? "✓" : s.violations || 0) + '</span></div><p class="text-gray-500 text-[10px]">' + (s.total_entities || 0) + " 实体 · " + (r.buildingType === "civil" ? "民用" : "工业") + "</p>" + bar + '<div class="mt-1 flex flex-wrap gap-0.5">' + badges + "</div>" + clauseText + "</div>";
    });
    fileHtml += "</div>";
    details.innerHTML = crossHtml + fileHtml;
  }
  if (typeof window !== "undefined") {
    const w2 = window;
    w2.runBatchReviewComponent = runBatchReview;
  }
  function downloadReviewPdf(reviewId) {
    const url = getApiBase() + "/api/v1/review/pdf?review_id=" + encodeURIComponent(reviewId);
    const key = getActiveKeyValue$1();
    const headers = {};
    if (key) headers["Authorization"] = "Bearer " + key;
    fetch(url, { headers }).then((resp) => {
      if (!resp.ok) {
        return resp.json().then((d) => {
          throw new Error(d.detail?.toString() || "下载失败 (" + resp.status + ")");
        });
      }
      return resp.blob();
    }).then((blob) => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "审查报告_" + (reviewId || "report") + ".pdf";
      a.click();
      URL.revokeObjectURL(a.href);
    }).catch((err) => {
      showToast$1("❌ " + err.message, "error");
    });
  }
  function downloadReviewExport(reviewId, format) {
    if (!reviewId) {
      showToast$1("没有可导出的审查结果", "info");
      return;
    }
    const url = getApiBase() + "/review/export?review_id=" + encodeURIComponent(reviewId) + "&format=" + format;
    fetch(url, { method: "GET", headers: getHeaders() }).then((resp) => {
      if (!resp.ok) return resp.json().then((d) => {
        throw new Error(d.detail?.toString() || resp.statusText);
      });
      return resp.blob();
    }).then((blob) => {
      const mime = format === "csv" ? "text/csv;charset=utf-8-sig" : "application/json";
      const ext = format === "csv" ? "csv" : "json";
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([blob], { type: mime }));
      a.download = "审查结果_" + reviewId + "." + ext;
      a.click();
      URL.revokeObjectURL(a.href);
      showToast$1("✅ 已导出 " + format.toUpperCase() + " 文件", "success");
    }).catch((e) => {
      showToast$1("❌ 导出失败: " + e.message, "error");
    });
  }
  function downloadReviewJSON() {
    const violations = window._reviewViolations || [];
    if (violations.length === 0) {
      showToast$1("没有可导出的审查结果", "info");
      return;
    }
    const exportData = {
      exportTime: (/* @__PURE__ */ new Date()).toISOString(),
      totalViolations: violations.length,
      violations: violations.map((v) => ({
        entity_id: v.entity_id,
        entity_type: v.entity_type,
        clause_id: v.clause_id,
        clause_title: v.clause_title,
        severity: v.severity || "major",
        result: v.result,
        extracted_value: v.extracted_value,
        required_value: v.required_value,
        difference: v.difference,
        explanation: v.explanation
      })),
      violationByClause: {}
    };
    violations.forEach((v) => {
      const cid = String(v.clause_id || "unknown");
      exportData.violationByClause[cid] = (exportData.violationByClause[cid] || 0) + 1;
    });
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "审查结果_" + (/* @__PURE__ */ new Date()).toISOString().slice(0, 10) + ".json";
    a.click();
    URL.revokeObjectURL(a.href);
  }
  async function loadFeedbackStats() {
    const el = document.getElementById("fb-stats");
    if (!el) return;
    try {
      const data = await apiGet("/api/v1/feedbacks/stats");
      if (data.status !== "success") throw new Error("加载失败");
      const s = data.stats;
      const byClause = s.by_clause || {};
      const topClauses = Object.entries(byClause).slice(0, 5).map(([c, n]) => "<p>" + escHtml$1(c) + ": " + String(n) + "条</p>").join("");
      const stats = s;
      el.innerHTML = '<div class="grid grid-cols-2 gap-2"><div class="card p-2 text-xs"><p class="font-medium">📊 申诉统计</p><p>总数: ' + stats.total + "</p><p>待审核: " + (stats.by_status?.pending || 0) + "</p><p>已接受: " + (stats.by_status?.accepted || 0) + "</p><p>已拒绝: " + (stats.by_status?.rejected || 0) + "</p><p>接受率: " + ((stats.accepted_rate || 0) * 100).toFixed(1) + '%</p></div><div class="card p-2 text-xs"><p class="font-medium">📋 高频条款</p>' + topClauses + "</div></div>";
    } catch (e) {
      el.textContent = "加载失败: " + e.message;
    }
  }
  async function loadFeedbacks() {
    const el = document.getElementById("fb-list");
    if (!el) return;
    try {
      const data = await apiGet("/api/v1/feedbacks");
      if (data.status !== "success") throw new Error("加载失败");
      const fbs = data.feedbacks || [];
      if (fbs.length === 0) {
        el.innerHTML = '<p class="text-gray-400 text-center py-4">暂无申诉记录</p>';
        return;
      }
      el.innerHTML = fbs.map((fb) => {
        const status = String(fb.status || "");
        const badge = status === "accepted" ? "bg-green-100 text-green-700" : status === "rejected" ? "bg-red-100 text-red-700" : "bg-yellow-100 text-yellow-700";
        const stxt = status === "accepted" ? "✅ 已接受" : status === "rejected" ? "❌ 已拒绝" : "⏳ 待审核";
        const reviewed = fb.reviewed_by ? '<p class="text-gray-400">审核: ' + escHtml$1(String(fb.reviewed_by)) + " - " + escHtml$1(String(fb.review_comment || "")) + "</p>" : "";
        return '<div class="card p-2 text-xs"><div class="flex items-center gap-2 mb-1"><span class="font-mono">' + escHtml$1(String(fb.feedback_id || "")) + '</span><span class="px-1.5 py-0.5 rounded text-xs ' + badge + '">' + stxt + '</span></div><p class="font-medium">' + escHtml$1(String(fb.clause_id || "")) + '</p><p class="text-gray-500">' + escHtml$1(String(fb.reason || "无理由")) + "</p>" + reviewed + '<p class="text-gray-400 text-xs">' + String(fb.created_at || "").slice(0, 10) + "</p></div>";
      }).join("");
    } catch (e) {
      el.innerHTML = '<p class="text-red-400 text-center py-4">加载失败: ' + e.message + "</p>";
    }
  }
  async function submitFeedback() {
    const val = (id) => document.getElementById(id)?.value?.trim() || "";
    const taskId = val("fb-task-id");
    const clauseId = val("fb-clause-id");
    const entityId = val("fb-entity-id");
    const reason = val("fb-reason");
    const description = val("fb-description");
    const originalValue = val("fb-original-value");
    const severity = val("fb-severity");
    if (!taskId || !clauseId || !reason) {
      showToast$1("请填写任务 ID、规范条款和申诉理由", "info");
      return;
    }
    try {
      const data = await apiFetch("/api/v1/feedbacks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task_id: taskId,
          clause_id: clauseId,
          entity_id: entityId,
          entity_type: "",
          reason,
          description,
          original_value: originalValue ? parseFloat(originalValue) : null,
          severity
        })
      });
      if (!data.status) throw new Error("提交失败");
      const fb = data.feedback;
      showToast$1("申诉提交成功！ID: " + (fb?.feedback_id || ""), "success");
      ["fb-task-id", "fb-clause-id", "fb-entity-id", "fb-reason", "fb-description", "fb-original-value", "fb-severity"].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.value = "";
      });
      loadFeedbackStats();
      loadFeedbacks();
    } catch (e) {
      showToast$1("提交失败: " + e.message, "error");
    }
  }
  let _diffResult = null;
  function _onDiffFileSelect(inputId, labelId) {
    const input = document.getElementById(inputId);
    const label = document.getElementById(labelId);
    if (!input || !label) return;
    input.addEventListener("change", () => {
      label.textContent = input.files && input.files[0] ? input.files[0].name : "";
    });
  }
  _onDiffFileSelect("diff-file1", "diff-file1-name");
  _onDiffFileSelect("diff-file2", "diff-file2-name");
  async function runDiffComparison() {
    const file1 = document.getElementById("diff-file1")?.files?.[0];
    const file2 = document.getElementById("diff-file2")?.files?.[0];
    if (!file1 || !file2) {
      showToast$1("请选择两个版本的图纸文件", "info");
      return;
    }
    const bt = document.getElementById("diff-building-type")?.value || "";
    const std = document.getElementById("diff-standard")?.value || "";
    const loading = document.getElementById("diff-loading");
    if (loading) {
      loading.className = "mt-3";
      renderProgress(loading, "审查并对比", 20);
    }
    try {
      const form = new FormData();
      form.append("file1", file1);
      form.append("file2", file2);
      const url = getApiBase() + "/review/compare?building_type=" + encodeURIComponent(bt) + "&standard=" + encodeURIComponent(std);
      const resp = await fetch(url, { method: "POST", headers: getReviewHeaders(), body: form });
      const data = await resp.json();
      if (loading) loading.className = "hidden";
      if (resp.status !== 200) {
        showToast$1("对比失败: " + (data.detail || JSON.stringify(data)), "error");
        return;
      }
      _diffResult = data;
      renderDiffResults(data);
    } catch (e) {
      if (loading) {
        loading.className = "mt-3 text-sm text-red-500";
        loading.innerHTML = "❌ 请求失败: " + e.message;
      }
    }
  }
  function renderDiffResults(data) {
    const s = data.summary || {};
    const empty = document.getElementById("diff-empty");
    const results = document.getElementById("diff-results");
    if (empty) empty.className = "hidden";
    if (results) results.className = "";
    const summaryDiv = document.getElementById("diff-summary");
    const newC = s.new_violations || 0;
    const fixedC = s.fixed_violations || 0;
    const changedC = s.changed_violations || 0;
    const totalV1 = s.total_v1 || 0;
    const totalV2 = s.total_v2 || 0;
    if (summaryDiv) {
      summaryDiv.innerHTML = '<div class="card p-3 text-center"><div class="text-lg font-bold text-blue-600">' + totalV1 + " → " + totalV2 + '</div><div class="text-xs text-gray-400">违规数</div></div><div class="card p-3 text-center"><div class="text-lg font-bold text-green-600">' + newC + '</div><div class="text-xs text-gray-400">🆕 新增违规</div></div><div class="card p-3 text-center"><div class="text-lg font-bold text-emerald-600">' + fixedC + '</div><div class="text-xs text-gray-400">✅ 已修复</div></div><div class="card p-3 text-center"><div class="text-lg font-bold text-yellow-600">' + changedC + '</div><div class="text-xs text-gray-400">🔄 变化项</div></div><div class="card p-3 text-center"><div class="text-lg font-bold ' + (newC === 0 ? "text-green-600" : "text-red-600") + '">' + (newC === 0 ? "✓ 合格" : newC + "项") + '</div><div class="text-xs text-gray-400">综合评估</div></div>';
    }
    const items = data.items || [];
    const groups = { new: [], fixed: [], changed: [] };
    items.forEach((item) => {
      const t = String(item.diff_type || "new");
      if (groups[t]) groups[t].push(item);
    });
    ["new", "fixed", "changed"].forEach((t) => renderDiffItemPanel(t, groups[t] || []));
    const rawEl = document.getElementById("diff-raw-json");
    if (rawEl) rawEl.textContent = JSON.stringify(data, null, 2);
    loadDiffVisualization(data);
    switchDiffTab("new");
  }
  function renderDiffItemPanel(type, items) {
    const el = document.getElementById("diff-items-" + type);
    if (!el) return;
    if (items.length === 0) {
      const labels = { new: "🆕 无新增违规", fixed: "✅ 无已修复项", changed: "🔄 无变化项" };
      el.innerHTML = '<div class="text-xs text-gray-400 py-4 text-center">' + (labels[type] || "无差异项") + "</div>";
      return;
    }
    let html = '<div class="flex items-center gap-2 mb-2"><span class="text-xs text-gray-500">共 ' + items.length + ' 项</span><span class="text-xs text-gray-400">|</span><span class="text-xs text-gray-400">严重: ' + items.filter((i) => i.severity === "critical").length + '</span><span class="text-xs text-gray-400">|</span><span class="text-xs text-gray-400">一般: ' + items.filter((i) => i.severity === "normal" || !i.severity).length + "</span></div>";
    html += '<table class="w-full text-xs"><thead><tr class="text-left text-gray-400 border-b"><th class="pb-1 pr-2">条款</th><th class="pb-1 pr-2">实体</th><th class="pb-1 pr-2">类型</th>';
    if (type === "new") html += '<th class="pb-1 pr-2">实测值</th><th class="pb-1 pr-2">要求值</th>';
    else if (type === "fixed") html += '<th class="pb-1 pr-2">原实测值</th><th class="pb-1 pr-2">要求值</th>';
    else html += '<th class="pb-1 pr-2">旧值</th><th class="pb-1 pr-2">新值</th>';
    html += '<th class="pb-1">严重度</th></tr></thead><tbody>';
    items.forEach((item) => {
      const sev = String(item.severity || "");
      const sevColor = sev === "critical" ? "red" : sev === "normal" ? "orange" : "gray";
      const sevLabel = sev === "critical" ? "严重" : sev === "normal" ? "一般" : "轻微";
      const oldV = item.old_value != null ? Number(item.old_value).toFixed(2) : "-";
      const newV = item.new_value != null ? Number(item.new_value).toFixed(2) : "-";
      const reqV = item.old_required != null ? item.old_required : item.new_required != null ? item.new_required : "-";
      html += '<tr class="border-b border-gray-50 hover:bg-gray-50"><td class="py-1.5 pr-2"><span title="' + escHtml$1(String(item.clause_title || "")) + '" class="cursor-help">' + escHtml$1(String(item.clause_id || "")) + '</span></td><td class="py-1.5 pr-2 truncate max-w-20" title="' + escHtml$1(String(item.entity_id || "")) + '">' + escHtml$1(String(item.entity_type || "-")) + '</td><td class="py-1.5 pr-2">' + (item.entity_id ? escHtml$1(String(item.entity_id).slice(0, 16)) : "-") + "</td>";
      if (type === "new") html += '<td class="py-1.5 pr-2 text-red-600">' + newV + '</td><td class="py-1.5 pr-2">' + reqV + "</td>";
      else if (type === "fixed") html += '<td class="py-1.5 pr-2 text-green-600 line-through">' + oldV + '</td><td class="py-1.5 pr-2">' + reqV + "</td>";
      else html += '<td class="py-1.5 pr-2 text-gray-400">' + oldV + '</td><td class="py-1.5 pr-2 text-yellow-600">' + newV + "</td>";
      html += '<td class="py-1.5"><span class="px-1.5 py-0.5 rounded text-xs bg-' + sevColor + "-100 text-" + sevColor + '-700">' + sevLabel + "</span></td></tr>";
      if (item.explanation) {
        html += '<tr class="border-b border-gray-50"><td colspan="7" class="pb-1.5 pl-4 text-gray-400 text-xs">💡 ' + escHtml$1(String(item.explanation).slice(0, 120)) + "</td></tr>";
      }
    });
    html += "</tbody></table>";
    el.innerHTML = html;
  }
  function switchDiffTab(tab) {
    ["new", "fixed", "changed"].forEach((t) => {
      const panel = document.getElementById("diff-items-" + t);
      if (panel) panel.className = "diff-items-panel" + (t === tab ? "" : " hidden");
    });
    document.querySelectorAll(".diff-tab-btn").forEach((btn) => {
      const isActive = btn.dataset.tab === tab;
      btn.className = "diff-tab-btn px-3 py-1 rounded-lg font-medium " + (isActive ? "bg-blue-100 text-blue-700" : "bg-gray-100 text-gray-600");
    });
  }
  function loadDiffVisualization(data) {
    const v1FileId = data.v1_file_id;
    const v2FileId = data.v2_file_id;
    const items = data.items || [];
    const v1El = document.getElementById("diff-vis-v1");
    const v2El = document.getElementById("diff-vis-v2");
    const makeUrl = (fileId, isV1 = false) => {
      if (!fileId) return null;
      const filtered = items.filter((item) => isV1 && item.diff_type === "fixed" || !isV1 && item.diff_type === "new");
      return getApiBase() + "/render/" + encodeURIComponent(fileId) + "/overlay?violations=" + encodeURIComponent(JSON.stringify(filtered.slice(0, 50).map((item) => ({
        entity_type: item.entity_type || "unknown",
        severity: item.severity || "major",
        clause_id: item.clause_id || "",
        x: 0,
        y: 0
      }))));
    };
    const v1Url = makeUrl(v1FileId, true);
    const v2Url = makeUrl(v2FileId, false);
    if (v1El && v1Url) {
      v1El.innerHTML = '<img src="' + v1Url + `" class="w-full" alt="版本1图纸" style="max-height:400px" onerror="this.outerHTML='<div class=text-center py-8 text-gray-400 text-xs>⚠️ 图纸渲染失败</div>'" />`;
    } else if (v1El) {
      v1El.innerHTML = '<div class="text-center py-8 text-gray-400 text-xs">无渲染数据</div>';
    }
    if (v2El && v2Url) {
      v2El.innerHTML = '<img src="' + v2Url + `" class="w-full" alt="版本2图纸" style="max-height:400px" onerror="this.outerHTML='<div class=text-center py-8 text-gray-400 text-xs>⚠️ 图纸渲染失败</div>'" />`;
    } else if (v2El) {
      v2El.innerHTML = '<div class="text-center py-8 text-gray-400 text-xs">无渲染数据</div>';
    }
  }
  function clearDiffResults() {
    const file1 = document.getElementById("diff-file1");
    const file2 = document.getElementById("diff-file2");
    if (file1) file1.value = "";
    if (file2) file2.value = "";
    const name1 = document.getElementById("diff-file1-name");
    const name2 = document.getElementById("diff-file2-name");
    if (name1) name1.textContent = "";
    if (name2) name2.textContent = "";
    const results = document.getElementById("diff-results");
    if (results) results.className = "hidden";
    const empty = document.getElementById("diff-empty");
    if (empty) {
      empty.className = "card text-center py-8 text-gray-300";
      empty.textContent = "上传两个版本的图纸后开始对比";
    }
    _diffResult = null;
  }
  const CLIMATE_NAMES = {
    severe_cold: "严寒",
    cold: "寒冷",
    hot_cold: "夏热冬冷",
    hot_warm: "夏热冬暖"
  };
  const THERMAL_THRESHOLDS = {
    severe_cold: { exterior_wall: 0.45, roof: 0.35, ground_floor: 0.3, exterior_window: 2 },
    cold: { exterior_wall: 0.6, roof: 0.5, ground_floor: 0.45, exterior_window: 2.4 },
    hot_cold: { exterior_wall: 1.5, roof: 1.2, ground_floor: 0.6, exterior_window: 3.2 },
    hot_warm: { exterior_wall: 2, roof: 1.5, ground_floor: 0.8, exterior_window: 4 }
  };
  const DEFAULT_THERMAL_THICKNESS = {
    exterior_wall: 50,
    roof: 60,
    ground_floor: 80,
    exterior_window: 30
  };
  function onThermalCompTypeChange() {
    const compType = document.getElementById("thermal-comp-type")?.value || "";
    const input = document.getElementById("thermal-thickness");
    if (input) input.value = String(DEFAULT_THERMAL_THICKNESS[compType] || 50);
  }
  function renderThermalThresholds() {
    const el = document.getElementById("thermal-thresholds");
    if (!el) return;
    let html = '<table class="w-full"><thead><tr class="text-gray-400 border-b"><th class="text-left py-1">气候带</th><th>外墙</th><th>屋顶</th><th>地面</th><th>外窗</th></tr></thead><tbody>';
    for (const [key, thresholds] of Object.entries(THERMAL_THRESHOLDS)) {
      html += '<tr class="border-b"><td class="py-1">' + escHtml$1(CLIMATE_NAMES[key] || key) + "</td>";
      for (const comp of ["exterior_wall", "roof", "ground_floor", "exterior_window"]) {
        html += '<td class="text-center">' + thresholds[comp].toFixed(2) + "</td>";
      }
      html += "</tr>";
    }
    html += "</tbody></table>";
    el.innerHTML = html;
  }
  async function computeThermalK() {
    const compType = document.getElementById("thermal-comp-type")?.value || "";
    const materialKey = document.getElementById("thermal-material")?.value || "";
    const thicknessMm = parseFloat(document.getElementById("thermal-thickness")?.value || "0");
    const climate = document.getElementById("thermal-climate")?.value || "";
    const resultDiv = document.getElementById("thermal-result");
    if (isNaN(thicknessMm) || thicknessMm <= 0) {
      if (resultDiv) resultDiv.innerHTML = '<span class="text-red-600">厚度无效</span>';
      return;
    }
    if (resultDiv) resultDiv.innerHTML = '<span class="text-gray-400">⏳ 计算中...</span>';
    try {
      const r = await fetch(getApiBase() + "/api/v1/review/thermal/k-value", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ compType, material: materialKey, thicknessMm, climate })
      });
      const data = await r.json();
      if (data.status !== "success") {
        if (resultDiv) resultDiv.innerHTML = '<span class="text-red-600">后端返回异常</span>';
        return;
      }
      const pass = Boolean(data.passed);
      let html = '<div class="mt-2 p-2 ' + (pass ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200") + ' rounded">';
      html += '<p class="font-medium ' + (pass ? "text-green-700" : "text-red-700") + '">';
      html += "K = " + data.K + " W/(m²·K) " + (pass ? "✅ ≤ " : "❌ > ") + data.threshold;
      html += "</p>";
      html += "<p>材料: " + data.material + " (λ=" + data.lambda + ") · 厚度: " + data.thicknessMm + "mm · R=" + data.R + " m²·K/W</p>";
      if (!pass) {
        html += '<p class="text-orange-600 mt-1">→ 改用当前材料需厚度 ≥ ' + data.requiredThicknessMm + "mm（当前差 " + data.additionalThicknessMm + "mm）</p>";
      } else {
        const climateLabel = CLIMATE_NAMES[data.climate] || String(data.climate);
        html += '<p class="text-gray-500 mt-1">→ 满足 GB55015-3.2.2 ' + climateLabel + " 要求</p>";
      }
      html += "</div>";
      if (resultDiv) resultDiv.innerHTML = html;
      try {
        localStorage.setItem("baa_last_thermal_result", JSON.stringify(data));
      } catch (_e) {
      }
    } catch (e) {
      if (resultDiv) resultDiv.innerHTML = '<span class="text-red-600">计算失败: ' + e.message + "</span>";
    }
  }
  function renderThermalViolations(thermalViolations) {
    const el = document.getElementById("thermal-review-list");
    if (!el) return;
    if (!thermalViolations || thermalViolations.length === 0) {
      el.innerHTML = '<span class="text-gray-400">✅ 单图审查后自动展示热工违规项</span>';
      return;
    }
    let html = '<p class="font-medium text-sm mb-1 text-orange-600">🌡️ 热工违规 (' + thermalViolations.length + "项)</p>";
    const corrs = window._currentReviewResult?.corrections || [];
    thermalViolations.forEach((f) => {
      const funcId = String(f.func_id || "THERM-xxx");
      const title = String(f.clause_title || f.description || "未知条款");
      const clauseId = String(f.clause_id || "");
      const actual = f.extracted_value ?? f.actual_value ?? "?";
      const required = f.required_value ?? f.threshold ?? "?";
      const sev = String(f.severity || "major");
      const sevColor = sev === "critical" ? "red" : sev === "major" ? "orange" : "yellow";
      const sevLabel = sev === "critical" ? "严重" : sev === "major" ? "主要" : "轻微";
      const conf = typeof f.confidence === "number" ? f.confidence : 1;
      const confPct = Math.round(conf * 100);
      const confColor2 = conf >= 0.85 ? "green" : conf >= 0.6 ? "yellow" : "red";
      const corrKey = String(f.clause_id || f.func_id || "").trim();
      const matchedCorrs = corrs.filter((c) => c.clause_id === corrKey);
      const hasCorr = matchedCorrs.length > 0;
      html += '<div class="p-1.5 rounded bg-' + sevColor + "-50 border-l-2 border-" + sevColor + '-400 mb-1">';
      html += '<div class="flex justify-between items-start"><p class="font-medium text-' + sevColor + '-700">' + escHtml$1(funcId) + '</p><div class="flex gap-1"><span class="px-1 rounded text-xs bg-' + sevColor + "-100 text-" + sevColor + '-700">' + sevLabel + '</span><span class="px-1 rounded text-xs bg-' + confColor2 + "-100 text-" + confColor2 + '-700" title="置信度 ' + confPct + '%">' + (conf >= 0.85 ? "高" : conf >= 0.6 ? "中" : "低") + '</span></div></div><p class="text-xs text-gray-600">' + escHtml$1(title) + '</p><p class="text-xs text-gray-500">实测: ' + (typeof actual === "number" ? actual.toFixed(3) : escHtml$1(String(actual))) + " · 要求: " + (typeof required === "number" ? required.toFixed(3) : escHtml$1(String(required))) + " · [" + escHtml$1(clauseId) + ']</p><div class="mt-1 bg-gray-200 rounded-full h-1 overflow-hidden"><div class="' + confColor2 + '-500 h-full rounded-full" style="width:' + confPct + '%"></div></div>';
      if (hasCorr) {
        const top = matchedCorrs[0];
        const pColor = String(top.priority) === "high" ? "red" : String(top.priority) === "medium" ? "orange" : "yellow";
        const pLabel = String(top.priority) === "high" ? "🔴 高" : String(top.priority) === "medium" ? "🟠 中" : "🟡 低";
        html += '<details class="mt-0.5"><summary class="cursor-pointer text-purple-600 font-medium text-xs">💡 修正建议 (' + matchedCorrs.length + '条)</summary><div class="mt-0.5 p-1 bg-' + pColor + "-50 rounded border-l-2 border-" + pColor + '-400"><p class="text-xs"><span class="text-' + pColor + '-600">' + pLabel + "</span> " + escHtml$1(String(top.recommendation)) + "</p></div></details>";
      }
      html += "</div>";
    });
    el.innerHTML = html;
  }
  async function generateCorrectionSuggestions() {
    const result = window._currentReviewResult;
    const entities = window._currentReviewEntities;
    if (!result || !entities) {
      showToast$1("请先运行审查", "info");
      return;
    }
    const rr = result;
    const findings = (rr.findings || []).filter((f) => f.result === "FAIL" && !f.is_duplicate);
    if (findings.length === 0) {
      const el = document.getElementById("correction-results");
      if (el) el.innerHTML = '<div class="text-green-600">✅ 无违规，无需修正建议</div>';
      return;
    }
    const panel = document.getElementById("review-correction-panel");
    const loading = document.getElementById("correction-loading");
    const resultsDiv = document.getElementById("correction-results");
    const btn = document.getElementById("correction-generate-btn");
    const modeSelect = document.getElementById("correction-mode-select");
    if (panel) panel.className = panel.className.replace(/hidden/g, "").trim();
    if (loading) loading.className = "";
    if (resultsDiv) resultsDiv.innerHTML = "";
    if (btn) {
      btn.disabled = true;
      btn.textContent = "...";
    }
    try {
      const mode = modeSelect?.value || "auto";
      const r = await fetch(getApiBase() + "/correction/suggestions", {
        method: "POST",
        headers: { ...getReviewHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ findings, entities, mode })
      });
      const data = await r.json();
      if (loading) loading.className = "hidden";
      const suggestions = data.suggestions;
      if (!suggestions || suggestions.length === 0) {
        if (resultsDiv) resultsDiv.innerHTML = '<div class="text-gray-500">未生成修正建议（规则引擎无匹配）</div>';
        return;
      }
      const priorityOrder = { high: 0, medium: 1, low: 2 };
      const sorted = suggestions.slice().sort((a, b) => (priorityOrder[String(a.priority)] ?? 3) - (priorityOrder[String(b.priority)] ?? 3));
      let html = '<p class="mb-1 text-gray-500">共 ' + sorted.length + " 条建议（" + mode + " 模式）</p>";
      for (const s of sorted) {
        const pColor = String(s.priority) === "high" ? "red" : String(s.priority) === "medium" ? "orange" : "yellow";
        const pLabel = String(s.priority) === "high" ? "🔴 高" : String(s.priority) === "medium" ? "🟠 中" : "🟡 低";
        html += '<div class="p-1.5 bg-gray-50 rounded border-l-2 border-' + pColor + '-400">';
        html += '<p class="font-medium"><span class="text-' + pColor + '-600">' + pLabel + "</span> [" + s.clause_id + "] " + s.description + "</p>";
        html += '<p class="text-gray-600 mt-0.5">💡 ' + s.recommendation + "</p>";
        if (Object.keys(s.parameters || {}).length > 0) {
          html += '<p class="text-xs text-gray-400 mt-0.5">参数: ' + JSON.stringify(s.parameters) + "</p>";
        }
        html += "</div>";
      }
      if (resultsDiv) resultsDiv.innerHTML = html;
    } catch (e) {
      if (loading) loading.className = "hidden";
      if (resultsDiv) resultsDiv.innerHTML = '<div class="text-red-600">生成失败: ' + e.message + "</div>";
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "生成";
      }
    }
  }
  function confirmCorrection(reviewId, corrIdx, accepted) {
    const key = "corr_" + reviewId + "_" + corrIdx;
    localStorage.setItem(key, accepted ? "accepted" : "rejected");
    const select = document.getElementById("compare-drawing-select");
    if (select && select.value) {
      const fn = window.onCompareSelect;
      if (typeof fn === "function") fn();
    }
  }
  const STRUCTURAL_PARAMS = {
    floor_live: { label: "楼面活荷载", clause: "GB50009-5.1.1", unit: "kN/㎡", threshold: { 住宅: 2, 办公: 2.5, 商业: 3.5, 图书馆: 4, 档案: 5, 车库: 2.5 }, op: ">=" },
    beam_reinforcement: { label: "梁最小配筋率", clause: "GB50010-9.2.1", unit: "%", threshold: { 默认: 0.2 }, op: ">=" },
    column_reinforcement: { label: "柱纵向配筋率下限", clause: "GB50010-11.4.12", unit: "%", threshold: { 抗震一级: 0.55, 抗震二级: 0.5, 抗震三级: 0.55, 抗震四级: 0.5 }, op: ">=" },
    foundation_depth: { label: "基础最小埋深", clause: "GB50007-5.1.3", unit: "m", threshold: { 默认: 0.5, 冻土区: 1 }, op: ">=" },
    slab_thickness: { label: "楼板最小厚度", clause: "GB50010-9.1.2", unit: "mm", threshold: { 默认: 80, 屋面板: 90 }, op: ">=" },
    beam_height: { label: "梁高跨比", clause: "GB50010-9.2.3", unit: "1/跨", threshold: { 简支: 0.083, 连续: 0.067 }, op: ">=" },
    concrete_strength: { label: "混凝土最低强度等级", clause: "GB50010-4.1.2", unit: "MPa", threshold: { 默认: 20, 预应力: 40 }, op: ">=" },
    seismic_grade: { label: "抗震等级标注", clause: "GB55008-3.2.1", unit: "有/无", threshold: { 必须: 1 }, op: "==" },
    seismic_intensity: { label: "抗震设防烈度", clause: "GB55008-3.1.1", unit: "度", threshold: { 最小: 6 }, op: ">=" },
    shear_wall_thickness: { label: "剪力墙最小厚度", clause: "GB55008-4.3.1", unit: "mm", threshold: { 默认: 160, 框支层: 200 }, op: ">=" },
    pile_count: { label: "柱下独立桩基数量", clause: "GB55008-4.1.1", unit: "根", threshold: { 默认: 2, 条形桩基: 3 }, op: ">=" }
  };
  function renderStructuralThresholds() {
    const el = document.getElementById("structural-thresholds");
    if (!el) return;
    let html = '<table class="w-full"><thead><tr class="text-gray-400 border-b"><th class="text-left py-1">构件</th><th>要求</th><th>单位</th><th>规范</th></tr></thead><tbody>';
    for (const [_key, p] of Object.entries(STRUCTURAL_PARAMS)) {
      const threshText = Object.entries(p.threshold).map(([k, v]) => k + ":" + v).join(" / ");
      html += '<tr class="border-b"><td class="py-1">' + escHtml$1(p.label) + '</td><td class="text-center">' + p.op + " " + threshText + '</td><td class="text-center">' + escHtml$1(p.unit) + '</td><td class="text-gray-500">' + escHtml$1(p.clause) + "</td></tr>";
    }
    html += "</tbody></table>";
    el.innerHTML = html;
  }
  function onStructuralCompTypeChange() {
    const type = document.getElementById("structural-comp-type")?.value || "";
    const p = STRUCTURAL_PARAMS[type];
    if (!p) return;
    const firstKey = Object.keys(p.threshold)[0];
    const input = document.getElementById("structural-value");
    if (input && firstKey) input.value = String(p.threshold[firstKey]);
  }
  async function computeStructuralCheck() {
    const compType = document.getElementById("structural-comp-type")?.value || "";
    const value = parseFloat(document.getElementById("structural-value")?.value || "0");
    const note = document.getElementById("structural-note")?.value || "";
    const resultDiv = document.getElementById("structural-result");
    if (isNaN(value)) {
      if (resultDiv) resultDiv.innerHTML = '<span class="text-red-600">输入值无效</span>';
      return;
    }
    const p = STRUCTURAL_PARAMS[compType];
    if (!p) return;
    let activeThreshold = null;
    let activeThresholdLabel = "";
    for (const [label, t] of Object.entries(p.threshold)) {
      if (note && note.includes(label)) {
        activeThreshold = t;
        activeThresholdLabel = label;
        break;
      }
    }
    if (activeThreshold === null) {
      const keys = Object.keys(p.threshold);
      activeThreshold = p.threshold[keys[0] || ""];
      activeThresholdLabel = keys[0] || "";
    }
    let passed = false;
    if (activeThreshold !== null) {
      if (p.op === ">=") passed = value >= activeThreshold;
      else if (p.op === "<=") passed = value <= activeThreshold;
      else if (p.op === "==") passed = value === activeThreshold;
      else if (p.op === ">") passed = value > activeThreshold;
      else if (p.op === "<") passed = value < activeThreshold;
      else passed = value === activeThreshold;
    }
    const sign = p.op === ">=" ? "≥" : p.op === "<=" ? "≤" : p.op === "==" ? "=" : p.op;
    let html = '<div class="mt-2 p-2 ' + (passed ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200") + ' rounded">';
    html += '<p class="font-medium ' + (passed ? "text-green-700" : "text-red-700") + '">';
    html += escHtml$1(p.label) + ": " + value + " " + p.unit + " " + (passed ? "✅ " : "❌ ") + sign + " " + activeThreshold + " " + p.unit;
    html += "</p>";
    html += '<p class="text-xs text-gray-500">规范: ' + p.clause + " · 适用条件: " + escHtml$1(activeThresholdLabel) + "</p>";
    if (!passed) {
      html += '<p class="text-orange-600 text-xs mt-1">→ 当前值不满足规范要求，建议修正至 ' + sign + " " + activeThreshold + " " + p.unit + "</p>";
    }
    html += "</div>";
    if (resultDiv) resultDiv.innerHTML = html;
  }
  function renderStructuralViolations(structuralViolations) {
    const el = document.getElementById("structural-review-list");
    if (!el) return;
    if (!structuralViolations || structuralViolations.length === 0) {
      el.innerHTML = '<span class="text-gray-400">✅ 单图审查后自动展示结构违规项</span>';
      return;
    }
    let html = "";
    structuralViolations.forEach((f) => {
      const funcId = String(f.func_id || "STR-xxx");
      const title = String(f.clause_title || f.description || "未知条款");
      const clauseId = String(f.clause_id || "");
      const actual = f.extracted_value ?? f.actual_value ?? "?";
      const required = f.required_value ?? f.threshold ?? "?";
      const isFail = f.result === "FAIL";
      html += '<div class="p-1.5 rounded ' + (isFail ? "bg-red-50 border-l-2 border-red-400" : "bg-green-50 border-l-2 border-green-400") + ' mb-1">';
      html += '<p class="font-medium ' + (isFail ? "text-red-700" : "text-green-700") + '">' + escHtml$1(funcId) + "</p>";
      html += '<p class="text-gray-600">' + escHtml$1(title) + "</p>";
      html += '<p class="text-xs text-gray-500">实测: ' + (typeof actual === "number" ? actual.toFixed(3) : escHtml$1(String(actual))) + " · 要求: " + (typeof required === "number" ? required.toFixed(3) : escHtml$1(String(required))) + " · [" + escHtml$1(clauseId) + "]</p>";
      html += "</div>";
    });
    el.innerHTML = html;
  }
  function escHtml(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  const HISTORY_PAGE_SIZE = 20;
  function _historyPage() {
    const w2 = window;
    return w2.historyPage || 0;
  }
  function _setHistoryPage(v) {
    const w2 = window;
    w2.historyPage = v;
  }
  function _getReviewResults$1() {
    const w2 = window;
    return w2.reviewResults || [];
  }
  function _setReviewResults(r) {
    const w2 = window;
    w2.reviewResults = r;
  }
  function renderHistoryList(resetPage = false) {
    if (resetPage) _setHistoryPage(0);
    const el = document.getElementById("history-list");
    if (!el) return;
    loadReviewResults();
    const search = (document.getElementById("history-search")?.value || "").toLowerCase();
    const filter = document.getElementById("history-filter")?.value || "all";
    const teamFilter = document.getElementById("history-team-filter")?.value || "";
    const projFilter = document.getElementById("history-project-filter")?.value || "";
    let filtered = _getReviewResults$1();
    if (filter === "civil") filtered = filtered.filter((r) => r.buildingType === "civil");
    else if (filter === "industrial") filtered = filtered.filter((r) => r.buildingType === "industrial");
    else if (filter === "violations") filtered = filtered.filter((r) => (r.violationCount || 0) > 0);
    else if (filter === "clean") filtered = filtered.filter((r) => (r.violationCount || 0) === 0);
    if (teamFilter) filtered = filtered.filter((r) => r.teamId === teamFilter);
    if (projFilter) filtered = filtered.filter((r) => r.projectId === projFilter);
    if (search) {
      filtered = filtered.filter(
        (r) => String(r.drawingName || "").toLowerCase().includes(search) || (r.details || []).some(
          (v) => String(v.clause_id || "").toLowerCase().includes(search) || String(v.clause_title || "").toLowerCase().includes(search)
        )
      );
    }
    const ctxEl = document.getElementById("history-context-info");
    if (ctxEl) {
      const w2 = window;
      const ctxParts = [];
      if (w2.currentTeamId) ctxParts.push("📌团队已选");
      if (w2.currentProjectId) ctxParts.push("📋项目已选");
      ctxEl.textContent = ctxParts.length ? ctxParts.join(" · ") : "";
    }
    _populateHistoryFilters();
    const totalPages = Math.ceil(filtered.length / HISTORY_PAGE_SIZE) || 1;
    if (_historyPage() >= totalPages) _setHistoryPage(totalPages - 1);
    const pageData = filtered.slice(_historyPage() * HISTORY_PAGE_SIZE, (_historyPage() + 1) * HISTORY_PAGE_SIZE);
    const countEl = document.getElementById("history-total-count");
    if (countEl) countEl.textContent = String(filtered.length);
    if (filtered.length === 0) {
      el.innerHTML = '<div class="text-center text-gray-400 py-8">无匹配记录</div>';
      return;
    }
    el.innerHTML = pageData.map((r) => {
      const viols = r.violationCount || r.details?.length || 0;
      const btLabel = r.buildingType === "civil" ? "民用" : r.buildingType === "industrial" ? "工业" : "--";
      const timeStr = new Date(String(r.reviewedAt || r.createdAt || Date.now())).toLocaleString();
      const color = viols === 0 ? "green" : "red";
      const teamTag = r.teamId ? '<span class="px-1 bg-blue-100 text-blue-600 rounded" title="团队">👥</span>' : "";
      const projTag = r.projectId ? '<span class="px-1 bg-purple-100 text-purple-600 rounded" title="项目">📋</span>' : "";
      const id = escHtml(String(r.id || ""));
      const name = escHtml(String(r.drawingName || ""));
      return `<div class="card p-3 hover:shadow-md transition-shadow"><div class="flex items-center justify-between"><div class="flex items-center gap-3 cursor-pointer flex-1" onclick="window.viewHistoryDetail('` + id + `')"><span class="text-` + color + '-500 text-lg">' + (viols === 0 ? "✅" : "🔴") + '</span><div><div class="font-medium text-sm">' + name + " " + teamTag + projTag + '</div><div class="text-xs text-gray-400">' + btLabel + " · " + timeStr + '</div></div></div><div class="text-right mr-3"><div class="text-sm font-bold text-' + color + '-600">' + viols + ' 项违规</div><div class="text-xs text-gray-400">💡 ' + (r.correctionCount || 0) + ` 条建议</div></div><button onclick="event.stopPropagation();window.deleteReviewRecord('` + id + `')" class="px-2 py-0.5 text-xs text-red-400 hover:text-red-600" title="删除">🗑️</button></div></div>`;
    }).join("") + renderPagination(totalPages);
  }
  function _populateHistoryFilters() {
    const teamSelect = document.getElementById("history-team-filter");
    const projSelect = document.getElementById("history-project-filter");
    const results = _getReviewResults$1();
    if (!results || results.length === 0) return;
    const teams = {};
    const projects = {};
    results.forEach((r) => {
      if (r.teamId) teams[String(r.teamId)] = String(r.teamId);
      if (r.projectId) projects[String(r.projectId)] = String(r.projectId);
    });
    if (teamSelect && Object.keys(teams).length > 0) {
      const curTeam = teamSelect.value || "";
      teamSelect.innerHTML = '<option value="">📌 全部团队</option>';
      Object.keys(teams).forEach((id) => {
        teamSelect.insertAdjacentHTML("beforeend", '<option value="' + escHtml(id) + '">' + escHtml(id.substring(0, 12)) + "</option>");
      });
      teamSelect.value = curTeam;
    }
    if (projSelect && Object.keys(projects).length > 0) {
      const curProj = projSelect.value || "";
      projSelect.innerHTML = '<option value="">📌 全部项目</option>';
      Object.keys(projects).forEach((id) => {
        projSelect.insertAdjacentHTML("beforeend", '<option value="' + escHtml(id) + '">' + escHtml(id.substring(0, 12)) + "</option>");
      });
      projSelect.value = curProj;
    }
  }
  function renderPagination(totalPages) {
    if (totalPages <= 1) return "";
    return '<div class="flex items-center justify-center gap-3 mt-4 text-sm"><button onclick="window.historyPage=Math.max(0,window.historyPage-1);window.renderHistoryList()" class="px-3 py-1 border rounded ' + (_historyPage() === 0 ? "opacity-50 cursor-not-allowed" : "hover:bg-gray-100") + '" ' + (_historyPage() === 0 ? "disabled" : "") + '>上一页</button><span class="text-gray-500">第 ' + (_historyPage() + 1) + " / " + totalPages + ' 页</span><button onclick="window.historyPage=Math.min(' + (totalPages - 1) + ',window.historyPage+1);window.renderHistoryList()" class="px-3 py-1 border rounded ' + (_historyPage() >= totalPages - 1 ? "opacity-50 cursor-not-allowed" : "hover:bg-gray-100") + '" ' + (_historyPage() >= totalPages - 1 ? "disabled" : "") + ">下一页</button></div>";
  }
  async function deleteReviewRecord(id) {
    if (!confirm("确定删除此审查记录？")) return;
    try {
      await fetch(getApiBase() + "/review/history/" + id, { method: "DELETE", headers: getHeaders() });
      const results = _getReviewResults$1().filter((r) => r.id !== id);
      _setReviewResults(results);
      renderHistoryList();
    } catch (_e) {
      const results = _getReviewResults$1().filter((r) => r.id !== id);
      _setReviewResults(results);
      renderHistoryList();
      showToast$1("已从本地移除（后端未找到该记录）", "info");
    }
  }
  async function viewHistoryDetail(id) {
    const r = _getReviewResults$1().find((x) => String(x.id) === id);
    if (!r) return;
    let modal = document.getElementById("history-detail-modal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "history-detail-modal";
      modal.className = "fixed inset-0 bg-black bg-opacity-40 z-50 flex items-center justify-center";
      modal.onclick = function(e) {
        if (e.target === modal) closeHistoryModal();
      };
      document.body.appendChild(modal);
    }
    const name = escHtml(String(r.drawingName || ""));
    modal.innerHTML = '<div class="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col"><div class="flex items-center justify-between p-4 border-b"><h3 class="text-lg font-bold">审查详情: ' + name + '</h3><button onclick="window.closeHistoryModal()" class="text-gray-400 hover:text-gray-600 text-xl">✕</button></div><div class="p-4 text-center text-gray-400">加载中...</div></div>';
    try {
      const resp = await fetch(getApiBase() + "/review/history/" + id, { headers: getHeaders() });
      const detail = await resp.json();
      if (!detail || detail.status === "error") {
        modal.innerHTML = '<div class="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4"><div class="p-4 text-center text-red-500">加载失败</div></div>';
        return;
      }
      const details = detail.details || [];
      const detailName = escHtml(String(detail.drawingName || r.drawingName || ""));
      const btLabel = detail.buildingType === "civil" ? "民用" : "工业";
      const reviewTime = new Date(String(detail.reviewedAt || r.reviewedAt)).toLocaleString();
      const criticalCount = details.filter((v) => v.severity === "critical").length || 0;
      const majorCount = details.filter((v) => v.severity === "major").length || 0;
      const minorCount = details.filter((v) => v.severity !== "critical" && v.severity !== "major").length || 0;
      let dm = '<div class="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col"><div class="flex items-center justify-between p-4 border-b"><h3 class="text-lg font-bold">审查详情: ' + detailName + '</h3><button onclick="window.closeHistoryModal()" class="text-gray-400 hover:text-gray-600 text-xl">✕</button></div><div class="p-4 overflow-y-auto flex-1"><div class="grid grid-cols-4 gap-3 mb-4"><div class="card p-2 text-center"><div class="text-lg font-bold text-blue-600">' + details.length + '</div><div class="text-xs text-gray-400">违规</div></div><div class="card p-2 text-center"><div class="text-lg font-bold text-red-600">' + criticalCount + '</div><div class="text-xs text-gray-400">严重</div></div><div class="card p-2 text-center"><div class="text-lg font-bold text-orange-600">' + majorCount + '</div><div class="text-xs text-gray-400">主要</div></div><div class="card p-2 text-center"><div class="text-lg font-bold text-yellow-600">' + minorCount + '</div><div class="text-xs text-gray-400">轻微</div></div></div><div class="text-xs text-gray-400 mb-2">建筑类型: ' + btLabel + " · 审查时间: " + reviewTime + '</div><div class="space-y-2">';
      details.slice().sort((a, b) => {
        const order = { critical: 0, major: 1 };
        return (order[String(a.severity)] !== void 0 ? order[String(a.severity)] : 2) - (order[String(b.severity)] !== void 0 ? order[String(b.severity)] : 2);
      }).slice(0, 50).forEach((v) => {
        const sevColor = v.severity === "critical" ? "red" : v.severity === "major" ? "orange" : "yellow";
        const sevLabel = v.severity === "critical" ? "严重" : v.severity === "major" ? "主要" : "轻微";
        dm += '<div class="p-2 bg-' + sevColor + '-50 rounded text-xs"><div class="flex justify-between"><span class="font-medium">' + escHtml(String(v.clause_title || "")) + '</span><span class="px-1.5 py-0.5 rounded bg-' + sevColor + "-100 text-" + sevColor + '-700">' + sevLabel + '</span></div><span class="text-gray-500">' + escHtml(String(v.clause_id || "")) + " · " + escHtml(String(v.entity_type || "")) + '</span><br/><span class="text-gray-400">' + escHtml(String(v.explanation || "")) + "</span></div>";
      });
      dm += (details.length > 50 ? '<div class="text-xs text-gray-400 text-center pt-2">... 仅显示前50项</div>' : "") + "</div>";
      const corrections = detail.corrections || [];
      if (corrections.length > 0) {
        dm += '<div class="mt-4 border-t pt-3"><p class="font-medium text-sm mb-2">💡 修正建议</p><div class="space-y-2">';
        corrections.slice(0, 20).forEach((c) => {
          const priColor = c.priority === "high" ? "red" : c.priority === "medium" ? "orange" : "green";
          dm += '<div class="p-2 bg-green-50 rounded text-xs"><span class="font-medium">' + escHtml(String(c.action || "")) + '</span> <span class="px-1.5 py-0.5 rounded bg-' + priColor + "-100 text-" + priColor + '-700">' + (c.priority || "low") + '</span><div class="text-gray-600 mt-1">' + escHtml(String(c.description || "")) + "</div>" + (c.recommendation ? '<div class="text-gray-500 mt-0.5">' + escHtml(String(c.recommendation)) + "</div>" : "") + "</div>";
        });
        dm += (corrections.length > 20 ? '<div class="text-xs text-gray-400 text-center">... 仅显示前20条</div>' : "") + "</div></div>";
      }
      dm += "</div></div></div>";
      modal.innerHTML = dm;
    } catch (e) {
      modal.innerHTML = '<div class="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4"><div class="p-4 text-center text-red-500">加载失败: ' + String(e) + "</div></div>";
    }
  }
  function closeHistoryModal() {
    const modal = document.getElementById("history-detail-modal");
    if (modal) modal.remove();
  }
  function clearReviewHistory() {
    if (!confirm("确定清空所有审查历史记录？此操作不可恢复。")) return;
    localStorage.removeItem("baa_review_results");
    _setReviewResults([]);
    fetch(getApiBase() + "/review/history", { method: "DELETE" }).catch(() => {
    });
    renderHistoryList();
    loadDashboard();
  }
  let statsCache = null;
  function _getReviewResults() {
    return window.reviewResults || [];
  }
  async function loadStats(days = 30) {
    try {
      const url = getApiBase() + `/api/v1/stats?days=${days}`;
      const r = await fetch(url, { headers: getHeaders() });
      if (r.ok) {
        const data = await r.json();
        if (data.status === "ok") {
          statsCache = data;
          return;
        }
      }
    } catch {
    }
    statsCache = null;
  }
  function renderOverviewCards() {
    const el = document.getElementById("overview-cards");
    if (!el) return;
    const overview = statsCache?.overview || {};
    const reviewResults = _getReviewResults();
    if (!overview.total_reviews && reviewResults.length) {
      const totalV = reviewResults.reduce((s, r) => s + (r.details.length || 0), 0);
      Object.assign(overview, {
        total_reviews: reviewResults.length,
        total_violations: totalV,
        avg_compliance_rate: reviewResults.filter((r) => (r.details.length || 0) === 0).length / reviewResults.length,
        avg_compliance_score: 0,
        avg_processing_time_ms: 0
      });
    }
    if (overview.total_reviews === 0) {
      el.innerHTML = '<div class="text-center text-gray-400 py-8">暂无审查数据</div>';
      return;
    }
    const passRate = (overview.avg_compliance_rate || 0) * 100;
    el.innerHTML = `<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;"><div class="card p-3 text-center"><div class="text-2xl font-bold text-blue-600">${overview.total_reviews}</div><div class="text-xs text-gray-500 mt-1">审查次数</div></div><div class="card p-3 text-center"><div class="text-2xl font-bold text-red-600">${overview.total_violations}</div><div class="text-xs text-gray-500 mt-1">违规总数</div></div><div class="card p-3 text-center"><div class="text-2xl font-bold text-green-600">${Math.round(passRate)}%</div><div class="text-xs text-gray-500 mt-1">平均合规率</div></div><div class="card p-3 text-center"><div class="text-2xl font-bold text-yellow-600">${overview.avg_compliance_score || "--"}</div><div class="text-xs text-gray-500 mt-1">平均得分</div></div><div class="card p-3 text-center"><div class="text-2xl font-bold text-purple-600">${Math.round(overview.avg_processing_time_ms || 0)}ms</div><div class="text-xs text-gray-500 mt-1">平均耗时</div></div></div>`;
  }
  function renderTrendChart() {
    const el = document.getElementById("trend-chart");
    if (!el) return;
    const trend = statsCache?.trend || [];
    if (!trend.length) {
      el.innerHTML = '<div class="text-gray-400 text-sm">暂无趋势数据</div>';
      return;
    }
    const maxH = Math.max(...trend.flatMap((t) => [t.violations, t.reviews]), 1);
    let bars = '<div style="flex:1;display:flex;align-items:flex-end;gap:4px;height:120px;border-bottom:1px solid #e5e7eb;padding-bottom:2px;">';
    trend.forEach((t) => {
      const hV = Math.round(t.violations / maxH * 115);
      const hR = Math.round(t.reviews / maxH * 115);
      const sd = t.date.length > 4 ? t.date.slice(5) : t.date;
      bars += `<div style="flex:1;min-width:30px;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;"><div style="display:flex;align-items:flex-end;gap:1px;"><div style="background:#ef4444;border-radius:2px 2px 0 0;width:10px;height:${hV}px"></div><div style="background:#3b82f6;border-radius:2px 2px 0 0;width:10px;height:${hR}px"></div></div><span style="font-size:9px;color:#9ca3af;margin-top:2px;">${sd}</span></div>`;
    });
    bars += "</div>";
    el.innerHTML = bars + `<div style="display:flex;justify-content:space-between;font-size:12px;color:#6b7280;margin-top:4px;"><div><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:#ef4444;margin-right:4px;"></span>违规<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:#3b82f6;margin-left:16px;margin-right:4px;"></span>审查</div><span style="color:#9ca3af;">峰值: ${maxH}</span></div>`;
  }
  function renderViolationDist() {
    const el = document.getElementById("violation-dist");
    if (!el) return;
    const dist = statsCache?.violation_distribution || {};
    const total = dist.critical + dist.major + dist.minor || 1;
    const items = [
      { label: "严重", count: dist.critical || 0, color: "#ef4444" },
      { label: "主要", count: dist.major || 0, color: "#f97316" },
      { label: "轻微", count: dist.minor || 0, color: "#eab308" }
    ];
    el.innerHTML = items.map(
      (s) => `<div class="flex items-center gap-2"><span class="w-10 text-xs">${s.label}</span><div class="flex-1 bg-gray-100 rounded-full h-4"><div class="h-4 rounded-full" style="width:${s.count / total * 100}%;background:${s.color}"></div></div><span class="w-6 text-right text-xs">${s.count}</span></div>`
    ).join("");
  }
  function renderConfidenceDist() {
    const el = document.getElementById("confidence-dist");
    if (!el) return;
    const dist = statsCache?.confidence_distribution || {};
    const total = dist.confirmed + dist.suspected + dist.needs_review || 1;
    const items = [
      { label: "确认", count: dist.confirmed || 0, color: "#22c55e" },
      { label: "疑似", count: dist.suspected || 0, color: "#f59e0b" },
      { label: "待复核", count: dist.needs_review || 0, color: "#ef4444" }
    ];
    el.innerHTML = items.map(
      (s) => `<div class="flex items-center gap-2"><span class="w-10 text-xs">${s.label}</span><div class="flex-1 bg-gray-100 rounded-full h-4"><div class="h-4 rounded-full" style="width:${s.count / total * 100}%;background:${s.color}"></div></div><span class="w-6 text-right text-xs">${s.count}</span></div>`
    ).join("");
  }
  function renderBuildingTypeDist() {
    const el = document.getElementById("building-type-dist");
    if (!el) return;
    const dist = statsCache?.building_type_distribution || {};
    const total = Object.values(dist).reduce((a, b) => a + b, 0) || 1;
    const items = [
      { label: "民用", count: dist.civil || 0, color: "#3b82f6" },
      { label: "工业", count: dist.industrial || 0, color: "#8b5cf6" }
    ];
    el.innerHTML = items.map(
      (s) => `<div class="flex items-center gap-2"><span class="w-10 text-xs">${s.label}</span><div class="flex-1 bg-gray-100 rounded-full h-4"><div class="h-4 rounded-full" style="width:${s.count / total * 100}%;background:${s.color}"></div></div><span class="w-6 text-right text-xs">${s.count}</span></div>`
    ).join("");
  }
  function renderEntityDist() {
    const el = document.getElementById("entity-dist");
    if (!el) return;
    const dist = statsCache?.entity_type_distribution || {};
    const items = Object.entries(dist).slice(0, 10);
    if (!items.length) {
      el.innerHTML = '<div class="text-gray-400 text-sm">暂无数据</div>';
      return;
    }
    const maxV = items[0][1];
    el.innerHTML = items.map(
      ([type, count]) => `<div class="flex items-center gap-2"><span class="w-20 text-xs font-mono truncate">${type}</span><div class="flex-1 bg-gray-100 rounded-full h-3"><div class="h-3 rounded-full bg-blue-500" style="width:${Math.round(count / maxV * 100)}%"></div></div><span class="text-xs">${count}</span></div>`
    ).join("");
  }
  function renderTopViolations() {
    const el = document.getElementById("top-violations");
    if (!el) return;
    const top = statsCache?.top_violations || [];
    if (!top.length) {
      el.innerHTML = '<div class="text-gray-400 text-sm">暂无数据</div>';
      return;
    }
    el.innerHTML = '<table class="w-full text-sm"><thead><tr class="text-left text-gray-400 border-b"><th class="pb-2 px-2">#</th><th class="pb-2 px-2">条款编号</th><th class="pb-2 px-2">条款标题</th><th class="pb-2 px-2 text-right">次数</th></tr></thead><tbody>' + top.map((v, i) => `<tr class="border-b border-gray-50"><td class="py-1 px-2 text-xs">${i + 1}</td><td class="py-1 px-2 font-mono text-xs">${v.clause_id}</td><td class="py-1 px-2 truncate max-w-64">${v.title || "--"}</td><td class="py-1 px-2 text-right text-sm font-medium text-red-600">${v.count}</td></tr>`).join("") + "</tbody></table>";
  }
  async function loadAnalysis(days = 30) {
    document.querySelectorAll('button[onclick^="loadAnalysis"]').forEach((btn) => {
      btn.classList.remove("bg-blue-100", "hover:bg-blue-200");
      btn.classList.add("hover:bg-gray-100");
      const match = btn.getAttribute("onclick")?.match(/loadAnalysis\((\d*)\)/);
      if (match) {
        const btnDays = match[1] ? parseInt(match[1]) : 0;
        if (btnDays === days || !match[1] && days === 30) {
          btn.classList.remove("hover:bg-gray-100");
          btn.classList.add("bg-blue-100", "hover:bg-blue-200");
        }
      }
    });
    await loadStats(days);
    renderOverviewCards();
    renderTrendChart();
    renderViolationDist();
    renderConfidenceDist();
    renderBuildingTypeDist();
    renderEntityDist();
    renderTopViolations();
  }
  function getReviewResults() {
    return window.reviewResults || [];
  }
  function renderAnalysisTable() {
    const tbody = document.getElementById("analysis-table");
    if (!tbody) return;
    const reviewResults = getReviewResults();
    if (reviewResults.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="py-8 text-center text-gray-300">暂无数据，请先审查图纸</td></tr>';
      return;
    }
    tbody.innerHTML = [...reviewResults].sort((a, b) => (b.violationCount || 0) - (a.violationCount || 0)).slice(0, 30).map((h, i) => {
      const viols = h.violationCount || 0;
      const checks = h.entityCount || 1;
      const passRate = checks > 0 ? Math.round((1 - viols / checks) * 100) : 0;
      const bt = h.buildingType;
      const btLabel = bt === "civil" ? "民用" : bt === "industrial" ? "工业" : "--";
      const safeName = escHtml$1(h.drawingName);
      return `<tr class="border-b border-gray-50 text-sm">
        <td class="py-2 px-2">${i + 1}</td>
        <td class="py-2 px-2 truncate max-w-32" title="${safeName}">${safeName}</td>
        <td class="py-2 px-2 text-xs">${btLabel}</td>
        <td class="py-2 px-2 text-red-600">${viols}</td>
        <td class="py-2 px-2"><div class="flex items-center gap-2">
          <div class="w-20 bg-gray-200 rounded-full h-2"><div class="bg-${passRate > 80 ? "green" : passRate > 50 ? "yellow" : "red"}-500 h-2 rounded-full" style="width:${Math.max(0, passRate)}%"></div></div>
          <span class="text-xs">${Math.max(0, passRate)}%</span></div></td>
        <td class="py-2 px-2 text-xs">${h.reviewedAt ? new Date(h.reviewedAt).toLocaleString("zh-CN") : "--"}</td></tr>`;
    }).join("");
  }
  function renderCategoryAnalysis() {
    const el = document.getElementById("category-analysis");
    if (!el) return;
    const reviewResults = getReviewResults();
    if (!reviewResults.length) {
      el.innerHTML = '<div class="text-gray-400 text-xs">审查图纸后自动统计</div>';
      return;
    }
    const catStats = {};
    reviewResults.forEach((h) => {
      const name = h.drawingName || "unknown";
      if (!catStats[name]) catStats[name] = { evac: 0, corridor: 0, dead_end: 0, other: 0 };
      h.details?.forEach((v) => {
        const fid = v.func_id || "";
        if (fid.startsWith("EVAC-")) catStats[name].evac++;
        else if (fid === "DIM-004") catStats[name].corridor++;
        else if ((v.explanation || "").toLowerCase().includes("死胡同")) catStats[name].dead_end++;
        else catStats[name].other++;
      });
    });
    const names = Object.keys(catStats);
    if (!names.length) {
      el.innerHTML = '<div class="text-gray-400 text-xs">审查图纸后自动统计</div>';
      return;
    }
    const totalEvac = names.reduce((s, n) => s + catStats[n].evac, 0);
    const totalCor = names.reduce((s, n) => s + catStats[n].corridor, 0);
    const totalDead = names.reduce((s, n) => s + catStats[n].dead_end, 0);
    const totalOther = names.reduce((s, n) => s + catStats[n].other, 0);
    let html = '<table class="w-full text-xs"><thead><tr class="text-left text-gray-400 border-b"><th class="pb-1 pr-2">图纸</th><th class="pb-1 pr-2">🚪疏散</th><th class="pb-1 pr-2">📏走廊</th><th class="pb-1 pr-2">🔒死胡同</th><th class="pb-1">其他</th></tr></thead><tbody>';
    names.forEach((name) => {
      const s = catStats[name];
      html += `<tr class="border-b border-gray-50">
      <td class="py-1 pr-2 truncate max-w-28" title="${name}">${name}</td>
      <td class="py-1 pr-2"><span class="${s.evac > 0 ? "text-red-600 font-medium" : "text-green-500"}">${s.evac}</span></td>
      <td class="py-1 pr-2"><span class="${s.corridor > 0 ? "text-orange-600 font-medium" : "text-green-500"}">${s.corridor}</span></td>
      <td class="py-1 pr-2"><span class="${s.dead_end > 0 ? "text-yellow-600 font-medium" : "text-green-500"}">${s.dead_end}</span></td>
      <td class="py-1">${s.other}</td></tr>`;
    });
    html += `<tr class="font-medium bg-gray-50"><td class="py-1 pr-2">合计</td><td class="py-1 pr-2">${totalEvac}</td><td class="py-1 pr-2">${totalCor}</td><td class="py-1 pr-2">${totalDead}</td><td class="py-1">${totalOther}</td></tr>`;
    html += "</tbody></table>";
    el.innerHTML = html;
  }
  function renderTrendBars() {
    const el = document.getElementById("trend-bars");
    if (!el) return;
    const reviewResults = getReviewResults();
    if (!reviewResults.length) {
      el.innerHTML = '<div class="text-gray-400">审查图纸后自动统计</div>';
      return;
    }
    const recent = reviewResults.slice(0, 20).reverse();
    const maxV = Math.max(...recent.map((r) => r.details.length || 0), 1);
    const totalV = recent.reduce((s, r) => s + (r.details.length || 0), 0);
    const avgV = Math.round(totalV / recent.length * 10) / 10;
    const cleanCount = recent.filter((r) => (r.details.length || 0) === 0).length;
    const firstD = new Date(recent[0]?.reviewedAt || Date.now()).toLocaleDateString();
    const lastD = new Date(recent[recent.length - 1]?.reviewedAt || Date.now()).toLocaleDateString();
    let chart = `<div class="grid grid-cols-4 gap-1 mb-2 text-xs"><div class="bg-blue-50 rounded p-1 text-center"><div class="text-blue-600 font-bold">${recent.length}</div><div class="text-gray-500 text-[10px]">审查次数</div></div><div class="bg-red-50 rounded p-1 text-center"><div class="text-red-600 font-bold">${totalV}</div><div class="text-gray-500 text-[10px]">违规总数</div></div><div class="bg-yellow-50 rounded p-1 text-center"><div class="text-yellow-600 font-bold">${avgV}</div><div class="text-gray-500 text-[10px]">平均违规/次</div></div><div class="bg-green-50 rounded p-1 text-center"><div class="text-green-600 font-bold">${recent.length - cleanCount}/${recent.length}</div><div class="text-gray-500 text-[10px]">有违规比率</div></div></div><div class="text-[10px] text-gray-400 mb-1"><span>📅 ${firstD} → ${lastD}</span><span>最大: ${maxV}</span></div>`;
    chart += '<div class="flex items-end gap-0.5 h-24 border-b border-gray-200 pb-0.5 overflow-x-auto">';
    recent.forEach((r) => {
      const v = r.details.length || 0;
      const pct = Math.round(v / maxV * 100);
      const height = Math.max(1, Math.round(pct / 100 * 96));
      const color = v === 0 ? "green" : v > maxV * 0.5 ? "red" : "orange";
      const name = (r.drawingName || "").slice(0, 10);
      chart += `<div class="flex-1 min-w-[24px] flex flex-col items-center"><div class="w-full bg-${color}-500 rounded-t" style="height:${height}px"></div><span class="text-[8px] text-gray-400 mt-0.5" title="${name}">${name.slice(0, 4)}</span></div>`;
    });
    chart += "</div>";
    el.innerHTML = chart;
  }
  function renderViolationDistBars() {
    const el = document.getElementById("violation-dist-bars");
    if (!el) return;
    const reviewResults = getReviewResults();
    if (!reviewResults.length) {
      el.innerHTML = '<div class="text-gray-400">审查图纸后自动统计</div>';
      return;
    }
    const sev = { critical: 0, major: 0, minor: 0 };
    reviewResults.forEach((r) => r.details?.forEach((v) => {
      if (v.severity === "critical") sev.critical++;
      else if (v.severity === "major") sev.major++;
      else sev.minor++;
    }));
    const total = sev.critical + sev.major + sev.minor || 1;
    el.innerHTML = [
      { label: "严重", count: sev.critical, color: "#ef4444" },
      { label: "主要", count: sev.major, color: "#f97316" },
      { label: "轻微", count: sev.minor, color: "#eab308" }
    ].map(
      (s) => `<div class="flex items-center gap-2"><span class="w-10 text-xs">${s.label}</span><div class="flex-1 bg-gray-100 rounded-full h-4"><div class="h-4 rounded-full" style="width:${s.count / total * 100}%;background:${s.color}"></div></div><span class="w-6 text-right text-xs">${s.count}</span></div>`
    ).join("");
  }
  const CD_MAJOR_LABELS = {
    arch: "建筑",
    struct: "结构",
    mech: "暖通",
    elec: "电气",
    plumb: "给排水"
  };
  const CD_LEVEL_COLORS = {
    L1: "red",
    L2: "orange",
    L3: "green"
  };
  const CD_METHOD_LABELS = {
    auto: "自动",
    manual: "人工",
    ai: "AI"
  };
  const CD_METHOD_ICONS = {
    auto: "🤖",
    manual: "👤",
    ai: "🦈"
  };
  async function loadCDItems() {
    const search = (document.getElementById("cd-search")?.value || "").toLowerCase();
    const level = document.getElementById("cd-filter-level")?.value || "all";
    const major = document.getElementById("cd-filter-major")?.value || "all";
    const method = document.getElementById("cd-filter-method")?.value || "all";
    const skel = document.getElementById("cd-skeleton");
    const content = document.getElementById("cd-content");
    if (skel) skel.classList.remove("hidden");
    if (content) content.classList.add("hidden");
    const parts = [];
    if (level !== "all") parts.push(`level=${encodeURIComponent(level)}`);
    if (major !== "all") parts.push(`major=${encodeURIComponent(major)}`);
    if (method !== "all") parts.push(`method=${encodeURIComponent(method)}`);
    const qs = parts.length ? `?${parts.join("&")}` : "";
    const path = `/api/v1/construction-review${qs}`;
    try {
      const data = await apiGet(path);
      if (skel) skel.classList.add("hidden");
      if (content) content.classList.remove("hidden");
      const items = data.items || [];
      let filtered = items;
      if (search) {
        filtered = items.filter(
          (i) => i.item_id.toLowerCase().includes(search) || i.title.toLowerCase().includes(search) || (i.description || "").toLowerCase().includes(search) || (i.standard_ref || "").toLowerCase().includes(search)
        );
      }
      const totalEl = document.getElementById("cd-total");
      const l1El = document.getElementById("cd-l1");
      const l2El = document.getElementById("cd-l2");
      const l3El = document.getElementById("cd-l3");
      if (totalEl) totalEl.textContent = String(data.summary?.total ?? items.length);
      if (l1El) l1El.textContent = String(data.summary.L1 ?? 0);
      if (l2El) l2El.textContent = String(data.summary.L2 ?? 0);
      if (l3El) l3El.textContent = String(data.summary.L3 ?? 0);
      const fc = document.getElementById("cd-filter-count");
      if (fc) fc.textContent = `${filtered.length} 项${filtered.length < items.length ? " / " + items.length : ""}`;
      const tbody = document.getElementById("cd-list");
      if (!tbody) return;
      if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="py-8 text-center text-gray-300">无匹配项</td></tr>';
        return;
      }
      tbody.innerHTML = filtered.map((i, idx) => {
        const lv = i.level || "L1";
        const majorLabel = CD_MAJOR_LABELS[i.major || ""] || i.major || "--";
        const methodLabel = CD_METHOD_LABELS[i.check_method || ""] || i.check_method || "--";
        const methodIcon = CD_METHOD_ICONS[i.check_method || ""] || "—";
        const funcId = i.func_id || '<span class="text-gray-400">—</span>';
        const color = CD_LEVEL_COLORS[lv] || "gray";
        return `<tr class="border-b border-gray-50">
          <td class="py-2 px-2 text-xs">${idx + 1}</td>
          <td class="py-2 px-2 font-mono text-xs text-blue-600">${i.item_id}</td>
          <td class="py-2 px-2 text-sm">${i.title}<br/><span class="text-xs text-gray-400">${i.description || ""}</span></td>
          <td class="py-2 px-2 font-mono text-xs text-gray-500">${i.standard_ref || ""}</td>
          <td class="py-2 px-2"><span class="px-2 py-0.5 bg-${color}-100 text-${color}-700 rounded text-xs">${lv}</span></td>
          <td class="py-2 px-2 text-xs">${majorLabel}</td>
          <td class="py-2 px-2 text-xs">${methodIcon} ${methodLabel}</td>
          <td class="py-2 px-2 font-mono text-xs">${funcId}</td>
        </tr>`;
      }).join("");
    } catch (e) {
      if (skel) skel.classList.add("hidden");
      if (content) content.classList.remove("hidden");
      const tbody = document.getElementById("cd-list");
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="8" class="py-8 text-center text-red-400">加载失败: ${e.message}</td></tr>`;
      }
    }
  }
  document.addEventListener("DOMContentLoaded", () => {
    const page = document.getElementById("page-cd");
    if (!page) return;
    const observer = new MutationObserver(() => {
      if (!page.classList.contains("hidden")) loadCDItems();
    });
    observer.observe(page, { attributes: true, attributeFilter: ["class"] });
  });
  const MODEL_PARAMS_TABS = {
    "functions": "原子函数参数",
    "layer-rules": "图层规则",
    "cd-items": "施工图审查标准",
    "samples": "审查样本",
    "export": "数据导出"
  };
  let _mpLoading = false;
  function _mpSetHTML(box, html) {
    if (!box) {
      _mpLoading = false;
      return;
    }
    box.classList.remove("hidden");
    box.style.display = "block";
    box.style.overflow = "auto";
    box.style.maxHeight = "480px";
    box.innerHTML = html;
    _mpLoading = false;
  }
  function _mpSetError(box, err) {
    const msg = err instanceof Error ? err.message : String(err);
    _mpSetHTML(box, `<p class="text-red-400 text-sm">加载失败: ${escHtml$1(msg)}</p>`);
  }
  async function _mpLoadFunctions() {
    const box = document.getElementById("mp-functions");
    try {
      const data = await apiGet("/api/v1/model-params/functions?limit=2000");
      const funcs = data.data || data.functions || [];
      if (funcs.length === 0) {
        _mpSetHTML(box, '<p class="text-gray-400 text-sm">无数据</p>');
        return;
      }
      const cats = {};
      funcs.forEach((f) => {
        const c = f.category || "other";
        cats[c] = (cats[c] || 0) + 1;
      });
      const summary = Object.keys(cats).slice(0, 12).map(
        (c) => `<span class="badge badge-sm badge-secondary">${escHtml$1(c)} ${cats[c]}</span>`
      ).join(" ");
      const rows = funcs.slice(0, 80).map(
        (f) => `<tr><td class="py-1 px-2 text-xs text-mono">${escHtml$1(f.func_id)}</td><td class="py-1 px-2 text-xs">${escHtml$1(f.title)}</td><td class="py-1 px-2 text-xs"><span class="badge badge-xs">${escHtml$1(f.category)}</span></td><td class="py-1 px-2 text-xs text-mono">${escHtml$1(f.clause_id)}</td><td class="py-1 px-2 text-xs">${escHtml$1(f.operator)} ${escHtml$1(f.threshold)}</td></tr>`
      ).join("");
      _mpSetHTML(
        box,
        `<div class="flex gap-2 mb-2 flex-wrap">${summary}</div><div class="text-xs text-gray-400 mb-2">显示 ${funcs.length} 个原子函数（前 80 条）</div><div class="overflow-auto"><table class="w-full text-sm"><thead class="bg-gray-50 text-xs text-gray-500"><tr><th class="py-1 px-2">#</th><th class="py-1 px-2">标题</th><th class="py-1 px-2">分类</th><th class="py-1 px-2">规范条款</th><th class="py-1 px-2">判定条件</th></tr></thead><tbody>${rows}</tbody></table></div>`
      );
    } catch (e) {
      _mpSetError(box, e);
    }
  }
  async function _mpLoadLayerRules() {
    const box = document.getElementById("mp-layer-rules");
    try {
      const data = await apiGet("/api/v1/model-params/layer-rules");
      const rules = data.data || data.rules || [];
      if (rules.length === 0) {
        _mpSetHTML(box, '<p class="text-gray-400 text-sm">无数据</p>');
        return;
      }
      const lr = rules.filter((r) => r.source === "LAYER_RULES").length;
      const sl = rules.filter((r) => r.source === "SHORT_LAYER_RULES").length;
      const rows = rules.slice(0, 60).map((r) => {
        const cls = r.source === "SHORT_LAYER_RULES" ? "badge-secondary" : "badge-primary";
        return `<tr><td class="py-1 px-2 text-xs text-mono">${escHtml$1(r.pattern)}</td><td class="py-1 px-2 text-xs">${escHtml$1(r.entity_type)}</td><td class="py-1 px-2 text-xs"><span class="badge badge-xs ${cls}">${escHtml$1(r.source)}</span></td><td class="py-1 px-2 text-xs">${escHtml$1(r.match_type)}</td></tr>`;
      }).join("");
      _mpSetHTML(
        box,
        `<div class="text-xs text-gray-400 mb-2">${rules.length} 条（LAYER_RULES: ${lr} / SHORT: ${sl}）前 60 条</div><div class="overflow-auto"><table class="w-full text-sm"><thead class="bg-gray-50 text-xs text-gray-500"><tr><th class="py-1 px-2">关键字</th><th class="py-1 px-2">实体类型</th><th class="py-1 px-2">来源</th><th class="py-1 px-2">匹配方式</th></tr></thead><tbody>${rows}</tbody></table></div>`
      );
    } catch (e) {
      _mpSetError(box, e);
    }
  }
  async function _mpLoadCDItems() {
    const box = document.getElementById("mp-cd-items");
    try {
      const data = await apiGet("/api/v1/model-params/cd-items");
      const items = data.data || data.items || [];
      if (items.length === 0) {
        _mpSetHTML(box, '<p class="text-gray-400 text-sm">无数据</p>');
        return;
      }
      const lvl = { L1: 0, L2: 0, L3: 0 };
      items.forEach((i) => {
        if (i.level && lvl[i.level] !== void 0) lvl[i.level]++;
      });
      const lvls = Object.keys(lvl).map((k) => {
        const cls = k === "L1" ? "text-red-500" : k === "L2" ? "text-orange-500" : "text-green-500";
        return `<span class="${cls}">${k}: ${lvl[k]}</span>`;
      }).join(" ");
      const rows = items.slice(0, 50).map(
        (i) => `<tr><td class="py-1 px-2 text-xs text-mono">${escHtml$1(i.item_id)}</td><td class="py-1 px-2 text-xs">${escHtml$1(i.title)}</td><td class="py-1 px-2 text-xs"><span class="badge badge-xs">${escHtml$1(i.level)}</span></td><td class="py-1 px-2 text-xs">${escHtml$1(i.major)}</td></tr>`
      ).join("");
      _mpSetHTML(
        box,
        `<div class="flex gap-3 mb-2 text-xs">${lvls}</div><div class="overflow-auto"><table class="w-full text-sm"><thead class="bg-gray-50 text-xs text-gray-500"><tr><th class="py-1 px-2">编码</th><th class="py-1 px-2">审查项</th><th class="py-1 px-2">等级</th><th class="py-1 px-2">专业</th></tr></thead><tbody>${rows}</tbody></table></div>`
      );
    } catch (e) {
      _mpSetError(box, e);
    }
  }
  async function _mpLoadSamples() {
    const box = document.getElementById("mp-samples");
    try {
      const data = await apiGet("/api/v1/model-params/samples?limit=20");
      const samples = data.data || data.samples || [];
      if (samples.length === 0) {
        _mpSetHTML(box, '<p class="text-yellow-500 text-sm">无样本数据（需有审查记录后自动生成）</p>');
        return;
      }
      const cards = samples.slice(0, 10).map(
        (s) => `<div class="card p-2 mb-2"><div class="text-xs text-gray-400">${escHtml$1(s.created_at)}</div><div class="text-sm font-medium">${escHtml$1(s.title ?? s.func_id ?? "样本")}</div><div class="text-xs text-mono">${escHtml$1(s.func_id)} | ${escHtml$1(s.dxf_file)}</div><div class="text-xs text-gray-500 mt-1">${s.query ? escHtml$1(s.query).slice(0, 200) : ""}</div></div>`
      ).join("");
      _mpSetHTML(box, `<div class="text-xs text-gray-400 mb-2">共 ${samples.length} 条（前 10 条）</div>` + cards);
    } catch (e) {
      _mpSetError(box, e);
    }
  }
  function switchModelParamTab(tab) {
    if (_mpLoading && tab !== "export") return;
    _mpLoading = true;
    Object.keys(MODEL_PARAMS_TABS).forEach((t) => {
      const btn = document.getElementById(`mptab-${t}`);
      const pane = document.getElementById(`mp-${t}`);
      if (btn) {
        btn.classList.toggle("active-tab", t === tab);
      }
      if (pane) {
        if (t === tab) {
          pane.classList.remove("hidden");
          pane.style.display = "block";
        } else {
          pane.classList.add("hidden");
          pane.style.display = "none";
        }
      }
    });
    if (tab === "functions") _mpLoadFunctions();
    else if (tab === "layer-rules") _mpLoadLayerRules();
    else if (tab === "cd-items") _mpLoadCDItems();
    else if (tab === "samples") _mpLoadSamples();
    else if (tab === "export") {
      _mpLoading = false;
      return;
    }
  }
  async function downloadModelExport(format) {
    try {
      const url = getApiBase() + `/api/v1/model-params/export?format=${encodeURIComponent(format)}`;
      window.open(url, "_blank");
      showToast$1(`已开始下载 ${format} 格式`);
    } catch (e) {
      showToast$1(`下载失败: ${e.message}`);
    }
  }
  function zoomImage(img) {
    if (!img || !img.src || img.style.display === "none") return;
    const old = document.getElementById("zoom-viewer");
    if (old) old.remove();
    const viewer = document.createElement("div");
    viewer.id = "zoom-viewer";
    viewer.className = "fixed inset-0 z-50 bg-black bg-opacity-90 select-none";
    viewer.innerHTML = '<div class="absolute inset-0 flex items-center justify-center overflow-hidden" id="zoom-stage"><img id="zoom-img" src="' + img.src + '" alt="" draggable="false" style="max-width:95vw;max-height:95vh;transition:transform .12s ease-out;cursor:grab" /></div><div class="absolute top-3 left-3 flex gap-1 z-10" id="zoom-toolbar"><button class="bg-white bg-opacity-80 text-gray-700 px-2.5 py-1 rounded text-sm hover:bg-opacity-100" onclick="zoomSet(1)">＋</button><button class="bg-white bg-opacity-80 text-gray-700 px-2.5 py-1 rounded text-sm hover:bg-opacity-100" onclick="zoomSet(-1)">－</button><button class="bg-white bg-opacity-80 text-gray-700 px-2.5 py-1 rounded text-sm hover:bg-opacity-100" onclick="zoomReset()" title="重置">⟲</button><button class="bg-white bg-opacity-80 text-gray-700 px-2.5 py-1 rounded text-sm hover:bg-opacity-100" onclick="zoomFit()" title="适应窗口">⊡</button><button class="bg-white bg-opacity-80 text-gray-700 px-2.5 py-1 rounded text-sm hover:bg-opacity-100" onclick="zoomClose()" title="关闭">✕</button><span id="zoom-scale" class="bg-white bg-opacity-80 text-gray-700 px-2 py-1 rounded text-xs self-center ml-1">100%</span></div><div class="absolute bottom-3 right-3 bg-black bg-opacity-50 text-gray-300 text-xs px-2 py-1 rounded" id="zoom-hint">滚轮缩放 · 拖拽平移 · ←↑→↓ · 空格/ESC 关闭</div>';
    document.body.appendChild(viewer);
    const imgEl = document.getElementById("zoom-img");
    const stage = document.getElementById("zoom-stage");
    const scaleEl = document.getElementById("zoom-scale");
    const state = { scale: 1, offsetX: 0, offsetY: 0, isDragging: false, lastX: 0, lastY: 0 };
    window.__zoomState = state;
    const apply = () => {
      if (!imgEl || !stage || !scaleEl) return;
      const x = state.offsetX + (stage.clientWidth - stage.clientWidth * state.scale) / 2;
      const y = state.offsetY + (stage.clientHeight - stage.clientHeight * state.scale) / 2;
      imgEl.style.transform = "translate(" + x.toFixed(1) + "px, " + y.toFixed(1) + "px) scale(" + state.scale.toFixed(4) + ")";
      imgEl.style.transformOrigin = "0 0";
      scaleEl.textContent = Math.round(state.scale * 100) + "%";
    };
    imgEl?.addEventListener("mousedown", (e) => {
      state.isDragging = true;
      state.lastX = e.clientX;
      state.lastY = e.clientY;
      imgEl.style.cursor = "grabbing";
      e.preventDefault();
    });
    window.addEventListener("mousemove", (e) => {
      if (!state.isDragging) return;
      state.offsetX += e.clientX - state.lastX;
      state.offsetY += e.clientY - state.lastY;
      state.lastX = e.clientX;
      state.lastY = e.clientY;
      apply();
    });
    window.addEventListener("mouseup", () => {
      state.isDragging = false;
      if (imgEl) imgEl.style.cursor = "grab";
    });
    stage?.addEventListener("wheel", (e) => {
      e.preventDefault();
      const delta = e.deltaY;
      const factor = delta < 0 ? 1.12 : 1 / 1.12;
      const newScale = Math.max(0.1, Math.min(20, state.scale * factor));
      const rect = stage.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const oldCx = state.offsetX + (rect.width - rect.width * state.scale) / 2;
      const oldCy = state.offsetY + (rect.height - rect.height * state.scale) / 2;
      const relX = (mx - oldCx) / state.scale;
      const relY = (my - oldCy) / state.scale;
      state.offsetX = mx - relX * newScale - (rect.width - rect.width * newScale) / 2;
      state.offsetY = my - relY * newScale - (rect.height - rect.height * newScale) / 2;
      state.scale = newScale;
      apply();
    }, { passive: false });
    viewer.addEventListener("click", (e) => {
      if (e.target === viewer || e.target === stage) zoomClose();
    });
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        zoomClose();
        return;
      }
      if (e.key === " ") {
        e.preventDefault();
        zoomClose();
        return;
      }
      if (e.key === "+" || e.key === "=") {
        zoomSet(1);
        return;
      }
      if (e.key === "-") {
        zoomSet(-1);
        return;
      }
      if (e.key === "ArrowLeft") {
        state.offsetX += 30;
        apply();
        e.preventDefault();
      }
      if (e.key === "ArrowRight") {
        state.offsetX -= 30;
        apply();
        e.preventDefault();
      }
      if (e.key === "ArrowUp") {
        state.offsetY += 30;
        apply();
        e.preventDefault();
      }
      if (e.key === "ArrowDown") {
        state.offsetY -= 30;
        apply();
        e.preventDefault();
      }
    });
    apply();
  }
  function zoomSet(dir) {
    const state = window.__zoomState;
    if (!state) return;
    const imgEl = document.getElementById("zoom-img");
    const stage = document.getElementById("zoom-stage");
    if (!imgEl || !stage) return;
    const factor = dir > 0 ? 1.25 : 0.8;
    const newScale = Math.max(0.1, Math.min(20, state.scale * factor));
    const rect = stage.getBoundingClientRect();
    const oldCx = state.offsetX + (rect.width - rect.width * state.scale) / 2;
    const oldCy = state.offsetY + (rect.height - rect.height * state.scale) / 2;
    state.offsetX = oldCx - (rect.width - rect.width * newScale) / 2;
    state.offsetY = oldCy - (rect.height - rect.height * newScale) / 2;
    state.scale = newScale;
    const x = state.offsetX + (rect.width - rect.width * state.scale) / 2;
    const y = state.offsetY + (rect.height - rect.height * state.scale) / 2;
    imgEl.style.transform = "translate(" + x.toFixed(1) + "px, " + y.toFixed(1) + "px) scale(" + state.scale.toFixed(4) + ")";
    imgEl.style.transformOrigin = "0 0";
    const s = document.getElementById("zoom-scale");
    if (s) s.textContent = Math.round(state.scale * 100) + "%";
  }
  function zoomReset() {
    const state = window.__zoomState;
    const imgEl = document.getElementById("zoom-img");
    if (!state || !imgEl) return;
    state.scale = 1;
    state.offsetX = 0;
    state.offsetY = 0;
    imgEl.style.transform = "none";
    const s = document.getElementById("zoom-scale");
    if (s) s.textContent = "100%";
  }
  function zoomFit() {
    zoomReset();
  }
  function zoomClose() {
    window.__zoomState = null;
    const el = document.getElementById("zoom-viewer");
    if (el) el.remove();
  }
  const _msSheetData = [];
  async function runMultiSheetReview() {
    const fileInput = document.getElementById("ms-file-input");
    const file = fileInput?.files?.[0];
    if (!file) {
      window.showToast("请先选择 DXF/DWG 文件", "info");
      return;
    }
    const btn = document.getElementById("ms-review-start-btn");
    const loading = document.getElementById("ms-review-loading");
    const results = document.getElementById("ms-review-results");
    if (!btn || !loading || !results) return;
    btn.disabled = true;
    btn.textContent = "⏳ 审查中...";
    loading.classList.remove("hidden");
    results.classList.add("hidden");
    const buildingType = document.getElementById("ms-building-type")?.value || "civil";
    const standard = document.getElementById("ms-standard")?.value || "GB 50016-2014";
    const formData = new FormData();
    formData.append("file", file);
    try {
      const url = getApiBase() + `/review-multi-sheet?building_type=${encodeURIComponent(buildingType)}&standard=${encodeURIComponent(standard)}`;
      const r = await fetch(url, { method: "POST", headers: getHeaders(), body: formData });
      const data = await r.json();
      if (!r.ok || data.status !== "success") {
        throw new Error(data.detail?.message || data.message || "审查失败");
      }
      _msSheetData.splice(0, _msSheetData.length, ...data.sheets || []);
      renderMultiSheetResults(data);
      results.classList.remove("hidden");
      loading.classList.add("hidden");
      btn.textContent = "📑 重新审查";
      btn.disabled = false;
    } catch (e) {
      loading.classList.add("hidden");
      btn.textContent = "📑 开始多Sheet审查";
      btn.disabled = false;
      window.showToast(`❌ 审查失败: ${e.message}`, "error");
    }
  }
  function renderMultiSheetResults(data) {
    const ps = data.project_summary || {};
    const sheets = data.sheets || [];
    const summaryEl = document.getElementById("ms-project-summary");
    if (summaryEl) {
      const rate = ps.compliance_rate;
      const passRate = rate !== void 0 ? (rate * 100).toFixed(1) : "--";
      const sev = ps.violations_by_severity || {};
      summaryEl.innerHTML = `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:12px;"><div class="card p-3 text-center"><div class="text-2xl font-bold text-indigo-600">${ps.sheet_count || 0}</div><div class="text-xs text-gray-500 mt-1">Sheet 数量</div></div><div class="card p-3 text-center"><div class="text-2xl font-bold text-blue-600">${ps.total_entities || 0}</div><div class="text-xs text-gray-500 mt-1">总实体</div></div><div class="card p-3 text-center"><div class="text-2xl font-bold text-red-600">${ps.total_violations || 0}</div><div class="text-xs text-gray-500 mt-1">总违规</div></div><div class="card p-3 text-center"><div class="text-2xl font-bold ${parseFloat(passRate) > 80 ? "text-green-600" : parseFloat(passRate) > 60 ? "text-yellow-600" : "text-red-600"}">${passRate}%</div><div class="text-xs text-gray-500 mt-1">合规率</div></div></div><div class="flex gap-4 text-xs text-gray-500"><span>🔴 严重: ${sev.critical || 0}</span><span>🟠 主要: ${sev.major || 0}</span><span>🟡 轻微: ${sev.minor || 0}</span><span>⏱ ${ps.processing_time_ms || 0}ms</span></div>`;
    }
    const tabsEl = document.getElementById("ms-sheet-tabs");
    if (tabsEl) {
      tabsEl.innerHTML = sheets.map((s, i) => {
        const vc = s.violation_count || 0;
        const badge = vc > 0 ? `<span class="text-red-500"> (${vc})</span>` : "";
        return `<button class="px-3 py-1.5 rounded-lg font-medium ${i === 0 ? "bg-indigo-100 text-indigo-700" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}" onclick="switchMultiSheetTab(${i})">${escHtml$1(s.name || "Sheet " + (i + 1))}${badge}</button>`;
      }).join("");
    }
    if (sheets.length > 0) renderMultiSheetTab(0);
  }
  function switchMultiSheetTab(index) {
    document.querySelectorAll("#ms-sheet-tabs button").forEach((btn, i) => {
      btn.className = `px-3 py-1.5 rounded-lg font-medium ${i === index ? "bg-indigo-100 text-indigo-700" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`;
    });
    renderMultiSheetTab(index);
  }
  function renderMultiSheetTab(index) {
    const el = document.getElementById("ms-sheet-detail");
    if (!el) return;
    const sheet = _msSheetData[index];
    if (!sheet) {
      el.innerHTML = '<div class="text-gray-400">无效的 Sheet 索引</div>';
      return;
    }
    const violations = sheet.violations || [];
    const vc = violations.length;
    if (vc === 0) {
      el.innerHTML = '<div class="text-center text-green-500 py-4">✅ 该 Sheet 无违规</div>';
      return;
    }
    const order = { critical: 0, major: 1, minor: 2 };
    violations.sort((a, b) => order[a.severity ?? 9] - order[b.severity ?? 9]);
    el.innerHTML = '<div class="text-xs space-y-2 max-h-96 overflow-y-auto">' + violations.map((v) => {
      const sev = v.severity;
      const label = sev === "critical" ? "🔴 严重" : sev === "major" ? "🟠 主要" : "🟡 轻微";
      const color = sev === "critical" ? "border-l-red-500" : sev === "major" ? "border-l-orange-400" : "border-l-yellow-400";
      return `<div class="border rounded p-2 ${color}" style="border-left-width:3px;"><div class="flex items-center justify-between"><span class="font-medium">${escHtml$1(v.clause_title || v.clause_id || "")}</span><span class="text-xs">${label}</span></div><div class="text-gray-500 mt-1">条款: <span class="font-mono">${escHtml$1(v.clause_id || "")}</span>${v.entity_type ? " · 实体: " + escHtml$1(v.entity_type) : ""}${v.extracted_value !== void 0 ? " · 实测: " + v.extracted_value : ""}${v.required_value !== void 0 ? " · 要求: " + v.required_value : ""}${v.difference !== void 0 ? " · 偏差: " + v.difference : ""}</div><div class="mt-1 text-xs bg-blue-50 p-1 rounded">💡 ${escHtml$1(v.correction || "")}</div></div>`;
    }).join("") + "</div>";
  }
  function formatTimeAgo(isoStr) {
    if (!isoStr) return "";
    const date = new Date(isoStr);
    const now = /* @__PURE__ */ new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMin = Math.floor(diffMs / 6e4);
    const diffHour = Math.floor(diffMs / 36e5);
    const diffDay = Math.floor(diffMs / 864e5);
    if (diffMin < 1) return "刚刚";
    if (diffMin < 60) return diffMin + "分钟前";
    if (diffHour < 24) return diffHour + "小时前";
    return diffDay + "天前";
  }
  function copyReverseDXF() {
    const dxf = document.getElementById("reverse-dxf");
    if (dxf) {
      navigator.clipboard.writeText(dxf.textContent).then(() => showToast$1("DXF 已复制到剪贴板", "info"));
    }
  }
  async function generateReverse() {
    const result = document.getElementById("reverse-result");
    const err = document.getElementById("reverse-error");
    if (!result) return;
    const constraints = document.getElementById("reverse-constraints");
    const validation = document.getElementById("reverse-validation");
    const dxfPre = document.getElementById("reverse-dxf");
    result.classList.add("hidden");
    err?.classList.add("hidden");
    const body = {
      room_type: document.getElementById("reverse-room-type")?.value || "office",
      width_mm: parseInt(document.getElementById("reverse-width")?.value || "0") || 5e3,
      height_mm: parseInt(document.getElementById("reverse-height")?.value || "0") || 4e3,
      door_width_mm: parseInt(document.getElementById("reverse-door-width")?.value || "0") || null
    };
    try {
      const resp = await fetch(getApiBase() + "/api/v1/reverse", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": "Bearer " + (getActiveKeyValue$1() || "") },
        body: JSON.stringify(body)
      });
      const data = await resp.json();
      if (data.status !== "ok") {
        err.textContent = "错误: " + JSON.stringify(data);
        err.classList.remove("hidden");
        return;
      }
      const c = data.constraints;
      if (constraints) {
        constraints.innerHTML = '<table class="w-full text-sm"><tr><td class="py-1 text-gray-500">最小宽度</td><td class="py-1">' + c.min_width_mm + ' mm</td></tr><tr><td class="py-1 text-gray-500">最小高度</td><td class="py-1">' + c.min_height_mm + ' mm</td></tr><tr><td class="py-1 text-gray-500">最小门宽</td><td class="py-1">' + c.min_door_width_mm + ' mm</td></tr><tr><td class="py-1 text-gray-500">面积</td><td class="py-1">' + c.min_area_m2.toFixed(1) + " m²</td></tr>" + (c.notes.length ? '<tr><td class="py-1 text-gray-500">规范约束</td><td class="py-1">' + c.notes.join("<br>") + "</td></tr>" : "") + "</table>";
      }
      const svgContainer = document.getElementById("reverse-svg");
      if (svgContainer && data.validation) {
        const singleLayout = {
          rooms: [{ type: body.room_type, x: 0, y: 0, w: body.width_mm, h: body.height_mm }],
          corridor: null
        };
        svgContainer.innerHTML = renderLayoutSVG(singleLayout, data.validation);
        window._reverseSVGLayout = singleLayout;
        window._reverseSVGValidation = data.validation;
      }
      const v = data.validation || {};
      if (validation) {
        validation.innerHTML = '<span class="' + (v.all_pass ? "text-green-600" : "text-red-600") + '" font-bold>' + (v.all_pass ? "✅ 闭环验证通过" : "❌ " + (v.fail_count || "?") + " FAIL") + "</span>";
      }
      if (dxfPre) dxfPre.textContent = data.dxf;
      result.classList.remove("hidden");
    } catch (e) {
      if (err) {
        err.textContent = "请求失败: " + e.message;
        err.classList.remove("hidden");
      }
    }
  }
  async function loadFunctions() {
    try {
      const resp = await fetch(getApiBase() + "/api/v1/functions", {
        headers: { "Authorization": "Bearer " + (getActiveKeyValue$1() || "") }
      });
      const data = await resp.json();
      if (data.status !== "ok") return;
      const countEl = document.getElementById("func-count");
      if (countEl) countEl.textContent = "共 " + data.count + " 个函数";
      const categories = /* @__PURE__ */ new Set();
      data.functions.forEach((f) => categories.add(f.category));
      const filter = document.getElementById("func-category-filter");
      if (filter) {
        categories.forEach((cat) => {
          const opt = document.createElement("option");
          opt.value = String(cat);
          opt.textContent = String(cat);
          filter.appendChild(opt);
        });
      }
      window._allFuncs = data.functions;
      filterFunctions();
    } catch (e) {
      const el = document.getElementById("func-list");
      if (el) el.innerHTML = '<div class="text-center text-red-500 py-8">加载失败: ' + e.message + "</div>";
    }
  }
  function filterFunctions() {
    const search = document.getElementById("func-search")?.value.toLowerCase() || "";
    const category = document.getElementById("func-category-filter")?.value || "";
    const funcs = window._allFuncs || [];
    const list = document.getElementById("func-list");
    if (!list) return;
    const filtered = funcs.filter((f) => {
      if (category && f.category !== category) return false;
      if (search && !f.func_id.toLowerCase().includes(search) && !f.name.toLowerCase().includes(search)) return false;
      return true;
    });
    list.innerHTML = filtered.map((f) => {
      const catColors = { dim: "blue", dist: "green", count: "purple", attr: "orange", exist: "red", area: "teal", evac: "pink", access: "indigo" };
      const color = catColors[f.category] || "gray";
      const fid = f.func_id;
      return '<div class="card p-3 hover:shadow-md transition cursor-pointer" onclick="toggleFuncDetail(&#39;' + fid + '&#39;)"><div class="flex items-center justify-between"><div class="flex items-center gap-2"><span class="text-xs font-mono bg-' + color + "-100 text-" + color + '-700 px-2 py-0.5 rounded">' + fid + '</span><span class="font-medium">' + f.name + '</span></div><span class="text-xs text-gray-400">' + f.clause_id + '</span></div><div class="text-sm text-gray-500 mt-1">' + f.description + '</div><div id="detail-' + fid + '" class="hidden mt-2 pt-2 border-t border-gray-100"><div class="grid grid-cols-2 gap-2 text-sm"><div><span class="text-gray-500">目标实体:</span> ' + (f.target_entities || []).join(", ") + '</div><div><span class="text-gray-500">运算符:</span> ' + f.operator + '</div><div><span class="text-gray-500">阈值:</span> <input class="input w-24 inline text-sm" value="' + f.threshold + '" id="th-' + fid + '" /></div><div><span class="text-gray-500">单位:</span> <input class="input w-20 inline text-sm" value="' + f.unit + '" id="unit-' + fid + '" /></div></div><button class="btn-primary text-xs mt-2" onclick="event.stopPropagation();updateFunction(&#39;' + fid + '&#39;)">保存修改</button></div></div>';
    }).join("");
  }
  function toggleFuncDetail(funcId) {
    document.getElementById("detail-" + funcId)?.classList.toggle("hidden");
  }
  async function updateFunction(funcId) {
    const th = document.getElementById("th-" + funcId);
    const unit = document.getElementById("unit-" + funcId);
    if (!th || !unit) return;
    try {
      await apiFetch("/api/v1/functions/" + funcId + "/update", {
        method: "POST",
        body: JSON.stringify({ threshold: parseFloat(th.value), unit: unit.value })
      });
      showToast$1("更新成功", "success");
    } catch (e) {
      showToast$1("更新失败: " + e.message, "error");
    }
  }
  function switchRevTab(tab) {
    const singlePanel = document.getElementById("rev-single-panel");
    const multiPanel = document.getElementById("rev-multi-panel");
    const tabSingle = document.getElementById("rev-tab-single");
    const tabMulti = document.getElementById("rev-tab-multi");
    if (tab === "multi") {
      singlePanel?.classList.add("hidden");
      multiPanel?.classList.remove("hidden");
      tabSingle?.classList.remove("bg-white", "shadow-sm", "font-medium");
      tabSingle?.classList.add("text-gray-600");
      tabMulti?.classList.add("bg-white", "shadow-sm", "font-medium");
      tabMulti?.classList.remove("text-gray-600");
      initMultiRooms();
    } else {
      singlePanel?.classList.remove("hidden");
      multiPanel?.classList.add("hidden");
      tabSingle?.classList.add("bg-white", "shadow-sm", "font-medium");
      tabSingle?.classList.remove("text-gray-600");
      tabMulti?.classList.remove("bg-white", "shadow-sm", "font-medium");
      tabMulti?.classList.add("text-gray-600");
    }
    document.getElementById("reverse-result")?.classList.add("hidden");
    document.getElementById("reverse-error")?.classList.add("hidden");
  }
  function initMultiRooms() {
    const list = document.getElementById("multi-room-list");
    if (!list || list.children.length > 0) return;
    addMultiRoom("office", 5e3, 4e3, 900);
    addMultiRoom("equipment", 3e3, 3e3, 900);
    addMultiRoom("accessible_toilet", 2500, 2500, 900);
  }
  function addMultiRoom(type, width, height, doorWidth) {
    const list = document.getElementById("multi-room-list");
    if (!list) return;
    const div = document.createElement("div");
    div.className = "multi-room-row flex items-center gap-2 mb-2 p-2 border rounded-lg bg-gray-50";
    div.innerHTML = '<select class="multi-room-type input text-sm w-28">' + ["office|办公室", "stair|楼梯间", "corridor|走廊", "exit|安全出口", "fire_lobby|前室", "equipment|设备间", "accessible_toilet|无障碍卫生间"].map((o) => {
      const [v, l] = o.split("|");
      return '<option value="' + v + '" ' + (v === type ? "selected" : "") + ">" + l + "</option>";
    }).join("") + '</select><input class="multi-room-width input text-sm w-20" value="' + width + '" placeholder="宽" /><input class="multi-room-height input text-sm w-20" value="' + height + '" placeholder="高" /><input class="multi-room-door-width input text-sm w-20" value="' + (doorWidth || "") + `" placeholder="门宽" /><span class="text-xs text-gray-400 w-16">mm</span><button class="text-red-500 hover:text-red-700 text-sm" onclick="this.closest('.multi-room-row').remove()">✕</button>`;
    list.appendChild(div);
  }
  async function generateMultiReverse() {
    const result = document.getElementById("reverse-result");
    const err = document.getElementById("reverse-error");
    if (!result) return;
    const dxfPre = document.getElementById("reverse-dxf");
    const validationDiv = document.getElementById("reverse-validation");
    result.classList.add("hidden");
    err?.classList.add("hidden");
    const rooms = [];
    document.querySelectorAll(".multi-room-row").forEach((row) => {
      rooms.push({
        room_type: row.querySelector(".multi-room-type")?.value || "office",
        width_mm: parseInt(row.querySelector(".multi-room-width")?.value || "0") || 5e3,
        height_mm: parseInt(row.querySelector(".multi-room-height")?.value || "0") || 4e3,
        door_width_mm: parseInt(row.querySelector(".multi-room-door-width")?.value || "0") || null
      });
    });
    if (rooms.length === 0) {
      rooms.push({ room_type: "office", width_mm: 5e3, height_mm: 4e3 });
      rooms.push({ room_type: "stair", width_mm: 3e3, height_mm: 5e3 });
    }
    try {
      const resp = await fetch(getApiBase() + "/api/v1/reverse/multi", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": "Bearer " + (getActiveKeyValue$1() || "") },
        body: JSON.stringify({ rooms, validate: true })
      });
      const data = await resp.json();
      if (data.status !== "ok") {
        err.textContent = "错误: " + JSON.stringify(data);
        err.classList.remove("hidden");
        return;
      }
      const svgContainer = document.getElementById("reverse-svg");
      if (svgContainer) {
        svgContainer.innerHTML = renderLayoutSVG(data.layout, data.validation);
        window._reverseSVGLayout = data.layout;
        window._reverseSVGValidation = data.validation;
      }
      const v = data.validation || {};
      if (validationDiv) {
        validationDiv.innerHTML = '<span class="' + (v.all_pass ? "text-green-600" : "text-gray-500") + ' font-bold">' + (v.all_pass ? "✅ 闭环验证通过" : "验证未开启") + "</span>";
      }
      if (dxfPre) dxfPre.textContent = data.dxf;
      result.classList.remove("hidden");
    } catch (e) {
      if (err) {
        err.textContent = "请求失败: " + e.message;
        err.classList.remove("hidden");
      }
    }
  }
  function renderLayoutSVG(layout, validation) {
    const rooms = layout.rooms || [];
    const corridor = layout.corridor;
    if (!rooms.length && !corridor) return '<div class="text-center text-gray-400 py-8">无布局数据</div>';
    const SCALE = 0.1;
    const MARGIN = 40;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    rooms.forEach((r) => {
      minX = Math.min(minX, r.x);
      minY = Math.min(minY, r.y);
      maxX = Math.max(maxX, r.x + r.w);
      maxY = Math.max(maxY, r.y + r.h);
    });
    if (corridor) {
      const ys = rooms.map((r) => r.y + r.h).concat(rooms.map((r) => r.y));
      const midY = Math.min(...ys);
      minX = Math.min(minX, 0);
      minY = Math.min(minY, midY - corridor.h);
      maxX = Math.max(maxX, corridor.w);
      maxY = Math.max(maxY, midY);
    }
    const svgW = (maxX - minX) * SCALE + MARGIN * 2;
    const svgH = (maxY - minY) * SCALE + MARGIN * 2;
    const colorMap = {
      office: "#dbeafe",
      stair: "#bfdbfe",
      corridor: "#e0f2fe",
      exit: "#bbf7d0",
      fire_lobby: "#fde68a",
      equipment: "#fed7aa",
      accessible_toilet: "#ddd6fe",
      bedroom: "#fce7f3",
      wc: "#f3e8ff",
      toilet: "#f3e8ff",
      hallway: "#ecfeff",
      kitchen: "#fef9c3",
      bathroom: "#e0e7ff"
    };
    const borderMap = {
      office: "#3b82f6",
      stair: "#2563eb",
      corridor: "#0891b2",
      exit: "#16a34a",
      fire_lobby: "#d97706",
      equipment: "#ea580c",
      accessible_toilet: "#7c3aed",
      bedroom: "#db2777",
      wc: "#8b5cf6",
      toilet: "#8b5cf6",
      hallway: "#06b6d4",
      kitchen: "#ca8a04",
      bathroom: "#6366f1"
    };
    let svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${svgW} ${svgH}" style="width:100%;height:100%;display:block;background:#fafafa" font-family="system-ui,sans-serif">`;
    svg += `<defs><marker id="arrow-evac" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto"><path d="M0,0 L8,3 L0,6" fill="#ef4444" stroke="#ef4444" stroke-width="0.5"/></marker></defs>`;
    rooms.forEach((r) => {
      const x = (r.x - minX) * SCALE + MARGIN;
      const y = (r.y - minY) * SCALE + MARGIN;
      const w2 = r.w * SCALE;
      const h = r.h * SCALE;
      const fill = colorMap[r.type] || "#e5e7eb";
      const stroke = borderMap[r.type] || "#6b7280";
      svg += `<rect x="${x}" y="${y}" width="${w2}" height="${h}" fill="${fill}" stroke="${stroke}" stroke-width="2" rx="2"/>`;
      const label = r.type.charAt(0).toUpperCase() + r.type.slice(1).replace(/_/g, " ");
      const labelFontSize = Math.max(9, Math.min(14, Math.min(w2, h) / 6));
      svg += `<text x="${x + w2 / 2}" y="${y + h / 2 - 4}" text-anchor="middle" font-size="${labelFontSize}" font-weight="600" fill="#1f2937">${label}</text>`;
      svg += `<text x="${x + w2 / 2}" y="${y + h / 2 + 10}" text-anchor="middle" font-size="8" fill="#6b7280">${r.w}x${r.h}mm</text>`;
    });
    if (corridor) {
      const ys = rooms.map((r) => r.y + r.h).concat(rooms.map((r) => r.y));
      const midY = Math.min(...ys);
      const cx = (0 - minX) * SCALE + MARGIN;
      const cy = (midY - corridor.h - minY) * SCALE + MARGIN;
      const cw = corridor.w * SCALE;
      const ch = corridor.h * SCALE;
      svg += `<rect x="${cx}" y="${cy}" width="${cw}" height="${ch}" fill="#e0f2fe" stroke="#0891b2" stroke-width="2" stroke-dasharray="6,4" rx="2"/>`;
      svg += `<text x="${cx + cw / 2}" y="${cy + ch / 2}" text-anchor="middle" font-size="11" font-weight="600" fill="#0e7490">CORRIDOR</text>`;
    }
    if (rooms.length > 1) {
      rooms.forEach((r) => {
        const doorYRoom = r.y + r.h;
        const corridorTop = Math.min(...rooms.map((rr) => rr.y + rr.h));
        const arrowStartX = (r.x + r.w / 2 - minX) * SCALE + MARGIN;
        const arrowStartY = (doorYRoom - minY) * SCALE + MARGIN + 4;
        const arrowEndX = arrowStartX;
        const arrowEndY = (corridorTop - minY) * SCALE + MARGIN - 4;
        if (arrowEndY > arrowStartY) {
          svg += `<line x1="${arrowStartX}" y1="${arrowStartY}" x2="${arrowEndX}" y2="${arrowEndY}" stroke="#ef4444" stroke-width="2" marker-end="url(#arrow-evac)"/>`;
        }
      });
      const corridorY2 = Math.min(...rooms.map((rr) => rr.y + rr.h));
      const corrCX = (0 + (corridor ? corridor.w : 3e3) / 2 - minX) * SCALE + MARGIN;
      const corrCY = (corridorY2 - minY) * SCALE + MARGIN;
      const exitX = (corridor ? corridor.w : 3e3) * SCALE + MARGIN;
      if (exitX > corrCX) {
        svg += `<line x1="${corrCX}" y1="${corrCY}" x2="${exitX - 20}" y2="${corrCY}" stroke="#ef4444" stroke-width="2" marker-end="url(#arrow-evac)"/>`;
        svg += `<text x="${exitX - 15}" y="${corrCY - 8}" text-anchor="middle" font-size="10" fill="#dc2626" font-weight="700">出口</text>`;
      }
    }
    if (validation && (validation.fail_count ?? 0) > 0) {
      svg += `<text x="${svgW / 2}" y="${svgH - 10}" text-anchor="middle" font-size="12" fill="#ef4444" font-weight="700">${validation.fail_count} 项违规</text>`;
    } else if (validation && validation.all_pass) {
      svg += `<text x="${svgW / 2}" y="${svgH - 10}" text-anchor="middle" font-size="12" fill="#16a34a" font-weight="700">闭环验证通过</text>`;
    }
    const scaleLen = 2e3 * SCALE;
    const scaleY = svgH - 25;
    svg += `<line x1="20" y1="${scaleY}" x2="${20 + scaleLen}" y2="${scaleY}" stroke="#374151" stroke-width="2"/>`;
    svg += `<line x1="20" y1="${scaleY - 4}" x2="20" y2="${scaleY + 4}" stroke="#374151" stroke-width="1.5"/>`;
    svg += `<line x1="${20 + scaleLen}" y1="${scaleY - 4}" x2="${20 + scaleLen}" y2="${scaleY + 4}" stroke="#374151" stroke-width="1.5"/>`;
    svg += `<text x="${20 + scaleLen / 2}" y="${scaleY - 6}" text-anchor="middle" font-size="8" fill="#6b7280">2m</text>`;
    svg += "</svg>";
    return svg;
  }
  function expandReverseSVG() {
    const layout = window._reverseSVGLayout;
    if (!layout) {
      showToast$1("先生成布局", "info");
      return;
    }
    const modal = document.createElement("div");
    modal.className = "fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4";
    modal.innerHTML = `<div class="bg-white rounded-lg shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col"><div class="flex items-center justify-between p-4 border-b"><h3 class="font-bold">布局可视化</h3><button onclick="this.closest('div.fixed').remove()" class="text-gray-400 hover:text-gray-600 text-2xl">&times;</button></div><div class="flex-1 overflow-auto p-4">` + renderLayoutSVG(layout, window._reverseSVGValidation) + "</div></div>";
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.remove();
    });
  }
  function downloadReverseSVG() {
    const svgEl = document.querySelector("#reverse-svg svg");
    if (!svgEl) {
      showToast$1("先生成布局", "info");
      return;
    }
    const blob = new Blob([svgEl.outerHTML], { type: "image/svg+xml" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "baa-layout.svg";
    a.click();
    URL.revokeObjectURL(a.href);
  }
  const _casePageSize = 15;
  async function loadCaseStats() {
    try {
      const r = await apiFetch("/api/v1/cases/stats");
      if (r.status !== "ok") return;
      const total = document.getElementById("case-total");
      const violations = document.getElementById("case-violations");
      const avgScore = document.getElementById("case-avg-score");
      const tagsCount = document.getElementById("case-tags-count");
      if (total) total.textContent = String(r.totalCases ?? "-");
      if (violations) violations.textContent = String(r.totalViolations ?? "-");
      if (avgScore) avgScore.textContent = String(r.avgScore ?? "-");
      if (tagsCount) tagsCount.textContent = String(r.topTags ? Object.keys(r.topTags).length : 0);
    } catch (e) {
      console.error("loadCaseStats failed:", e);
    }
  }
  async function loadCases(page = 0) {
    const q = document.getElementById("case-search")?.value || "";
    const bt = document.getElementById("case-filter-type")?.value || "";
    const tag = document.getElementById("case-filter-tag")?.value || "";
    const listEl = document.getElementById("case-list");
    if (listEl) listEl.innerHTML = '<div class="text-center text-gray-400 py-8">加载中...</div>';
    try {
      let data;
      if (q) {
        data = await apiFetch(`/api/v1/cases/search?q=${encodeURIComponent(q)}`);
      } else {
        const params = new URLSearchParams({ limit: String(_casePageSize), offset: String(page * _casePageSize) });
        if (bt) params.set("building_type", bt);
        if (tag) params.set("tag", tag);
        data = await apiFetch(`/api/v1/cases?${params}`);
      }
      if (data.status !== "ok") {
        if (listEl) listEl.innerHTML = '<div class="text-center text-gray-400 py-8">加载失败</div>';
        return;
      }
      const cases = data.cases || [];
      renderCaseList(cases, data.total ?? 0);
      renderCasePagination(data.total ?? 0, page);
    } catch (e) {
      console.error("loadCases failed:", e);
      if (listEl) listEl.innerHTML = '<div class="text-center text-red-400 py-8">加载失败: ' + e.message + "</div>";
    }
  }
  function renderCaseList(cases, total) {
    const el = document.getElementById("case-list");
    if (!el) return;
    if (cases.length === 0) {
      el.innerHTML = '<div class="text-center text-gray-400 py-8">暂无案例数据</div>';
      return;
    }
    const tagColors = {
      "尺寸不合规": "bg-red-100 text-red-700",
      "距离不合规": "bg-orange-100 text-orange-700",
      "数量不合规": "bg-yellow-100 text-yellow-700",
      "缺失设施": "bg-red-100 text-red-700",
      "面积不合规": "bg-blue-100 text-blue-700",
      "属性不合规": "bg-gray-100 text-gray-700",
      "照明不合规": "bg-yellow-100 text-yellow-700",
      "无障碍不合规": "bg-green-100 text-green-700"
    };
    let html = "";
    for (const c of cases) {
      const score = c.score ?? 0;
      const scoreColor = score >= 80 ? "text-green-600" : score >= 50 ? "text-yellow-600" : "text-red-600";
      const violations = c.violationCount ?? 0;
      const corrections = c.correctionCount ?? 0;
      const tagsHtml = (c.tags || []).slice(0, 4).map(
        (t) => `<span class="inline-block px-2 py-0.5 text-xs rounded-full ${tagColors[t] || "bg-gray-100 text-gray-600"}">${escHtml$1(t)}</span>`
      ).join(" ");
      html += `<div class="card p-4 hover:bg-gray-50 cursor-pointer transition" onclick="openCaseDetail('${escHtml$1(c.caseId)}')">
      <div class="flex items-center justify-between mb-2">
        <div><h4 class="font-medium text-sm">${escHtml$1(c.drawingName)}</h4>
        <span class="text-xs text-gray-400">${escHtml$1(c.buildingType || "civil")} · ${escHtml$1(c.standard || "")}</span></div>
        <div class="text-right"><span class="${scoreColor} font-bold text-lg">${score.toFixed(0)}</span><span class="text-xs text-gray-400 ml-1">分</span></div>
      </div>
      ${tagsHtml ? `<div class="flex flex-wrap gap-1 mb-2">${tagsHtml}</div>` : ""}
      <div class="flex gap-4 text-xs text-gray-400">
        <span>图元 ${c.entityCount ?? "-"}</span>
        <span class="${violations > 0 ? "text-red-500" : "text-green-500"}">违规 ${violations}</span>
        <span class="text-blue-500">修正 ${corrections}</span>
        <span>${formatTimeAgo(c.reviewedAt || "")}</span>
      </div></div>`;
    }
    el.innerHTML = html;
  }
  function renderCasePagination(total, page) {
    const el = document.getElementById("case-pagination");
    if (!el) return;
    const totalPages = Math.ceil(total / _casePageSize);
    if (totalPages <= 1) {
      el.innerHTML = "";
      return;
    }
    let html = "";
    html += `<button onclick="loadCases(${page - 1})" ${page === 0 ? "disabled" : ""} class="px-3 py-1 border rounded text-sm ${page === 0 ? "opacity-40" : "hover:bg-gray-100"}">← 上一页</button>`;
    html += `<span class="px-2 text-sm text-gray-500">第 ${page + 1} / ${totalPages} 页</span>`;
    html += `<button onclick="loadCases(${page + 1})" ${page + 1 >= totalPages ? "disabled" : ""} class="px-3 py-1 border rounded text-sm ${page + 1 >= totalPages ? "opacity-40" : "hover:bg-gray-100"}">下一页 →</button>`;
    el.innerHTML = html;
  }
  async function openCaseDetail(caseId) {
    const titleEl = document.getElementById("case-detail-title");
    const contentEl = document.getElementById("case-detail-content");
    const modal = document.getElementById("case-detail-modal");
    if (!modal || !titleEl || !contentEl) return;
    titleEl.textContent = "案例详情";
    contentEl.innerHTML = '<div class="text-center text-gray-400 py-8">加载中...</div>';
    modal.classList.remove("hidden");
    try {
      const data = await apiFetch(`/api/v1/cases/${caseId}`);
      if (data.status !== "ok") {
        contentEl.innerHTML = `<div class="text-center text-red-400 py-8">${escHtml$1(data.message || "加载失败")}</div>`;
        return;
      }
      const score = data.score ?? 0;
      const scoreColor = score >= 80 ? "text-green-600" : score >= 50 ? "text-yellow-600" : "text-red-600";
      const tagsHtml = (data.tags || []).map(
        (t) => `<span class="inline-block px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-700">${escHtml$1(t)}</span>`
      ).join(" ");
      let html = `<div class="mb-4">
      <h4 class="font-bold">${escHtml$1(data.drawingName)}</h4>
      <p class="text-xs text-gray-400">${escHtml$1(data.buildingType || "civil")} · ${escHtml$1(data.standard || "")} · ${formatTimeAgo(data.reviewedAt || "")}</p>
      <div class="mt-2 flex gap-2 flex-wrap">${tagsHtml}</div></div>
      <div class="grid grid-cols-3 gap-3 mb-4">
        <div class="card p-3 text-center"><div class="${scoreColor} font-bold text-xl">${score.toFixed(0)}</div><div class="text-xs text-gray-500">审查得分</div></div>
        <div class="card p-3 text-center"><div class="font-bold text-xl text-red-500">${data.violationCount ?? "-"}</div><div class="text-xs text-gray-500">违规数</div></div>
        <div class="card p-3 text-center"><div class="font-bold text-xl text-blue-500">${data.correctionCount ?? "-"}</div><div class="text-xs text-gray-500">修正建议</div></div></div>
      <h5 class="font-medium mb-2">核心违规 TOP-5</h5><div class="space-y-2">`;
      for (const v of data.topViolations || []) {
        const tierColor = v.confidence_tier === "高" ? "text-red-600" : v.confidence_tier === "中" ? "text-yellow-600" : "text-gray-400";
        html += `<div class="border rounded p-2 text-sm">
        <div class="font-medium">${escHtml$1(v.clause_title || v.clause_id)}</div>
        <div class="text-xs text-gray-400">${escHtml$1(v.entity_type || "")} · 条款 ${escHtml$1(v.clause_id || "")}</div>
        ${v.extracted_value !== void 0 ? `<div class="text-xs">实测 ${v.extracted_value} · 要求 ${v.required_value} · 偏差 ${v.difference}</div>` : ""}
        ${v.confidence_tier ? `<span class="${tierColor} text-xs">${v.confidence_tier}置信</span>` : ""}</div>`;
      }
      if (!data.topViolations || data.topViolations.length === 0) {
        html += '<div class="text-center text-gray-400 text-sm py-4">无违规记录</div>';
      }
      html += "</div>";
      contentEl.innerHTML = html;
    } catch (e) {
      contentEl.innerHTML = `<div class="text-center text-red-400 py-8">加载失败: ${escHtml$1(e.message)}</div>`;
    }
  }
  function closeCaseDetail() {
    const modal = document.getElementById("case-detail-modal");
    if (modal) modal.classList.add("hidden");
  }
  if (typeof document !== "undefined") {
    document.addEventListener("click", function(e) {
      const modal = document.getElementById("case-detail-modal");
      if (modal && !modal.classList.contains("hidden") && e.target === modal) {
        closeCaseDetail();
      }
    });
    setTimeout(loadFunctions, 1e3);
  }
  let _token = localStorage.getItem("baa_collab_token") || "";
  let _user = {};
  try {
    _user = JSON.parse(localStorage.getItem("baa_collab_user") || "{}");
  } catch (_) {
  }
  function collabErrMsg(d) {
    if (!d) return "请求失败";
    if (typeof d === "string") return d;
    const obj = d;
    if (typeof obj.detail === "string") return obj.detail;
    if (obj.detail && typeof obj.detail === "object") {
      const det = obj.detail;
      return String(det.message || det.error_code || "请求失败");
    }
    return "请求失败";
  }
  function collabApi(path, options) {
    const opts = { ...options };
    const url = getApiBase() + path;
    const headers = { "Content-Type": "application/json" };
    if (_token) headers["Authorization"] = "Bearer " + _token;
    if (opts.headers) {
      const extra = opts.headers;
      for (const k in extra) headers[k] = extra[k];
    }
    opts.headers = headers;
    return fetch(url, opts).then((r) => {
      if (r.status === 401 && _token && opts.autoLogout !== false) collabLogout();
      return r.json().catch(() => ({}));
    });
  }
  function closeCollabModal() {
    const el = document.getElementById("collab-modal-overlay");
    if (el) el.style.display = "none";
  }
  function setModalBody(html) {
    const el = document.getElementById("collab-modal-body");
    if (el) {
      el.innerHTML = html;
      const o = document.getElementById("collab-modal-overlay");
      if (o) o.style.display = "flex";
    }
  }
  function _tabStyle(active) {
    const btns = document.querySelectorAll("#collab-auth-tabs button");
    if (btns.length < 2) return;
    btns[0].className = active ? "flex-1 px-4 py-2 rounded text-sm font-medium bg-blue-500 text-white" : "flex-1 px-4 py-2 rounded text-sm font-medium bg-gray-100 text-gray-600";
    btns[1].className = active ? "flex-1 px-4 py-2 rounded text-sm font-medium bg-gray-100 text-gray-600" : "flex-1 px-4 py-2 rounded text-sm font-medium bg-blue-500 text-white";
  }
  function showCollabLogin() {
    const f = document.getElementById("collab-login-form");
    if (f) f.style.display = "block";
    const r = document.getElementById("collab-register-form");
    if (r) r.style.display = "none";
    _tabStyle(true);
  }
  function showCollabRegister() {
    const f = document.getElementById("collab-login-form");
    if (f) f.style.display = "none";
    const r = document.getElementById("collab-register-form");
    if (r) r.style.display = "block";
    _tabStyle(false);
  }
  function collabLogin() {
    const u = document.getElementById("collab-username")?.value?.trim() || "";
    const p = document.getElementById("collab-password")?.value || "";
    if (!u || !p) {
      const m = document.getElementById("collab-auth-msg");
      if (m) m.textContent = "请输入用户名和密码";
      return;
    }
    collabApi("/collab/auth/login", { method: "POST", body: JSON.stringify({ username: u, password: p }), autoLogout: false }).then((d) => {
      if (d.status === "success") {
        _token = String(d.token || "");
        _user = d.user || {};
        localStorage.setItem("baa_collab_token", _token);
        localStorage.setItem("baa_collab_user", JSON.stringify(_user));
        const m = document.getElementById("collab-auth-msg");
        if (m) m.textContent = "";
        collabEnterMain();
      } else {
        const m = document.getElementById("collab-auth-msg");
        if (m) m.textContent = collabErrMsg(d);
      }
    }).catch((e) => {
      const m = document.getElementById("collab-auth-msg");
      if (m) m.textContent = "网络错误: " + e.message;
    });
  }
  function collabRegister() {
    const u = document.getElementById("collab-reg-username")?.value?.trim() || "";
    const p = document.getElementById("collab-reg-password")?.value || "";
    const e = document.getElementById("collab-reg-email")?.value?.trim() || "";
    const dn = document.getElementById("collab-reg-name")?.value?.trim() || "";
    if (!u || !p) {
      const m = document.getElementById("collab-reg-msg");
      if (m) m.textContent = "用户名和密码不能为空";
      return;
    }
    if (p.length < 6) {
      const m = document.getElementById("collab-reg-msg");
      if (m) m.textContent = "密码至少6位";
      return;
    }
    const body = { username: u, password: p };
    if (e) {
      body.email = e;
      body.display_name = dn;
    }
    collabApi("/collab/auth/register", { method: "POST", body: JSON.stringify(body), autoLogout: false }).then((d) => {
      if (d.status === "success") {
        const m = document.getElementById("collab-reg-msg");
        if (m) {
          m.textContent = "注册成功，请登录";
          m.style.color = "#059669";
        }
        showCollabLogin();
        const un = document.getElementById("collab-username");
        if (un) un.value = u;
      } else {
        const m = document.getElementById("collab-reg-msg");
        if (m) m.textContent = collabErrMsg(d);
      }
    }).catch((err) => {
      const m = document.getElementById("collab-reg-msg");
      if (m) m.textContent = "网络错误: " + err.message;
    });
  }
  function collabLogout() {
    _token = "";
    _user = {};
    localStorage.removeItem("baa_collab_token");
    localStorage.removeItem("baa_collab_user");
    updateUserStatus(false);
    const ms = document.getElementById("collab-main-section");
    if (ms) ms.style.display = "none";
    const ls = document.getElementById("collab-login-section");
    if (ls) ls.style.display = "block";
  }
  function collabEnterMain() {
    const ls = document.getElementById("collab-login-section");
    if (ls) ls.style.display = "none";
    const ms = document.getElementById("collab-main-section");
    if (ms) ms.style.display = "block";
    const d = document.getElementById("collab-user-display");
    if (d) d.textContent = "👤 " + String(_user.display_name || _user.username || "");
    collabRefresh();
    updateUserStatus(true);
  }
  function updateUserStatus(loggedIn) {
    const lo = document.getElementById("user-status-logged-out");
    const li = document.getElementById("user-status-logged-in");
    if (!lo || !li) return;
    if (loggedIn) {
      const ne = document.getElementById("user-status-name");
      if (ne) ne.textContent = "👤 " + String(_user.display_name || _user.username || "—");
      const re = document.getElementById("user-status-role");
      if (re) re.textContent = String(_user.role || "user");
    }
    lo.style.display = loggedIn ? "none" : "block";
    li.style.display = loggedIn ? "flex" : "none";
  }
  function collabRefresh() {
    loadCollabStats();
    loadCollabTeams();
  }
  function loadCollabStats() {
    collabApi("/collab/stats").then((d) => {
      if (d.status !== "success") return;
      const s = d.stats;
      const ue = document.getElementById("cs-users");
      if (ue) ue.textContent = String(s.users || 0);
      const te = document.getElementById("cs-teams");
      if (te) te.textContent = String(s.teams || 0);
      const pe = document.getElementById("cs-projects");
      if (pe) pe.textContent = String(s.active_projects || 0);
      const se = document.getElementById("cs-sessions");
      if (se) se.textContent = String(s.review_sessions || 0);
    });
  }
  function loadCollabTeams() {
    collabApi("/collab/teams").then((d) => {
      const el = document.getElementById("collab-teams");
      if (!el) return;
      if (d.status !== "success") {
        el.innerHTML = "加载失败";
        return;
      }
      const teams = d.teams || [];
      if (!teams.length) {
        el.innerHTML = "暂无团队";
        return;
      }
      let h = '<table class="collab-table"><tr><th>名称</th><th>成员</th><th>角色</th><th>时间</th><th>操作</th></tr>';
      for (const t of teams) {
        h += "<tr><td><strong>" + escHtml$1(String(t.name)) + "</strong></td><td>" + String(t.member_count ?? "") + '</td><td><span class="collab-badge collab-badge-' + String(t.my_role) + '">' + String(t.my_role) + "</span></td><td>" + new Date(Number(t.created_at) * 1e3).toLocaleDateString() + `</td><td><button class="text-blue-600 text-xs underline" onclick="showTeamDetail('` + String(t.id) + `')">📋</button></td></tr>`;
      }
      h += "</table>";
      el.innerHTML = h;
    });
  }
  function showCreateTeamModal() {
    setModalBody('<h3 class="text-lg font-bold mb-4">新建团队</h3><input id="modal-team-name" class="input w-full mb-2" placeholder="团队名称" /><textarea id="modal-team-desc" class="input w-full mb-3" placeholder="描述" rows="2"></textarea><div class="flex gap-2 justify-end"><button class="modal-btn modal-btn-secondary" onclick="closeCollabModal()">取消</button><button class="modal-btn modal-btn-primary" onclick="createTeam()">创建</button></div>');
  }
  function createTeam() {
    const name = document.getElementById("modal-team-name")?.value?.trim() || "";
    if (!name) return;
    const desc = document.getElementById("modal-team-desc")?.value?.trim() || "";
    collabApi("/collab/teams", { method: "POST", body: JSON.stringify({ name, description: desc }) }).then((d) => {
      if (d.status === "success") {
        window.setCurrentTeamId?.(String(d.team_id || d.id || ""));
        window.setCurrentProjectId?.("");
        closeCollabModal();
        collabRefresh();
      } else {
        showToast$1(collabErrMsg(d), "info");
      }
    });
  }
  function showTeamDetail(teamId) {
    window.setCurrentTeamId?.(teamId);
    window.setCurrentProjectId?.("");
    Promise.all([collabApi("/collab/teams/" + teamId), collabApi("/collab/teams/" + teamId + "/projects")]).then((r) => {
      if (r[0].status !== "success") return;
      const team = r[0].team || {};
      const projects = r[1].projects || [];
      const members = team.members || [];
      let mh = '<table class="collab-table"><tr><th>用户</th><th>角色</th><th>时间</th></tr>';
      for (const m of members) {
        mh += "<tr><td>" + escHtml$1(String(m.display_name || m.username || "")) + '</td><td><span class="collab-badge collab-badge-' + String(m.role) + '">' + String(m.role) + "</span></td><td>" + new Date(Number(m.joined_at) * 1e3).toLocaleDateString() + "</td></tr>";
      }
      mh += "</table>";
      let ph = "";
      if (!projects.length) {
        ph = '<p class="text-sm text-gray-400 py-2">暂无项目</p>';
      } else {
        ph = '<table class="collab-table"><tr><th>项目</th><th>图纸</th><th>审查</th><th>状态</th><th>操作</th></tr>';
        for (const p of projects) {
          ph += "<tr><td><strong>" + escHtml$1(String(p.name)) + "</strong></td><td>" + String(p.file_count ?? "") + "</td><td>" + String(p.review_count ?? "") + "</td><td>" + String(p.status) + `</td><td><button class="text-blue-600 text-xs underline" onclick="showProjectDetail('` + String(p.id) + `')">📝</button></td></tr>`;
        }
        ph += "</table>";
      }
      setModalBody('<h3 class="text-lg font-bold mb-4">团队: ' + escHtml$1(String(team.name)) + '</h3><div class="mb-4"><h4 class="font-medium mb-2">成员 (' + members.length + ")</h4>" + mh + `</div><div><div class="flex justify-between items-center mb-2"><h4 class="font-medium">项目</h4><button class="modal-btn modal-btn-primary text-xs" onclick="showCreateProjectModal('` + teamId + `')">+ 新建项目</button></div>` + ph + '</div><div class="flex gap-2 justify-end mt-4"><button class="modal-btn modal-btn-secondary" onclick="closeCollabModal()">关闭</button></div>');
    });
  }
  function showProjectDetail(projectId) {
    window.setCurrentProjectId?.(projectId);
    Promise.all([collabApi("/collab/projects/" + projectId), collabApi("/collab/projects/" + projectId + "/review-sessions")]).then((r) => {
      if (r[0].status !== "success") return;
      const proj = r[0].project || {};
      const sessions = r[1].review_sessions || [];
      const members = proj.members || [];
      let mh = '<table class="collab-table"><tr><th>用户</th><th>权限</th></tr>';
      for (const m of members) {
        mh += "<tr><td>" + escHtml$1(String(m.display_name || m.username || "")) + '</td><td><span class="collab-badge">' + String(m.permission) + "</span></td></tr>";
      }
      mh += "</table>";
      let sh = "";
      if (!sessions.length) {
        sh = '<p class="text-sm text-gray-400 py-2">暂无审查会话</p>';
      } else {
        sh = '<table class="collab-table"><tr><th>名称</th><th>状态</th><th>创建人</th><th>时间</th><th>操作</th></tr>';
        for (const s of sessions) {
          sh += "<tr><td>" + escHtml$1(String(s.name)) + '</td><td><span class="collab-badge collab-badge-' + String(s.status) + '">' + String(s.status) + "</span></td><td>" + escHtml$1(String(s.creator_name || "")) + "</td><td>" + new Date(Number(s.created_at) * 1e3).toLocaleString() + `</td><td><button class="text-blue-600 text-xs underline" onclick="showReviewSessionDetail('` + String(s.id) + `')">📝</button></td></tr>`;
        }
        sh += "</table>";
      }
      setModalBody('<h3 class="text-lg font-bold mb-4">项目: ' + escHtml$1(String(proj.name)) + '</h3><div class="mb-4"><h4 class="font-medium mb-2">成员</h4>' + mh + `</div><div><div class="flex justify-between items-center mb-2"><h4 class="font-medium">审查会话</h4><button class="modal-btn modal-btn-primary text-xs" onclick="showCreateReviewSessionModal('` + projectId + `' )">+ 新建审查</button></div>` + sh + '</div><div class="flex gap-2 justify-end mt-4"><button class="modal-btn modal-btn-secondary" onclick="closeCollabModal()">关闭</button></div>');
    });
  }
  function showCreateProjectModal(teamId) {
    setModalBody(`<h3 class="text-lg font-bold mb-4">新建项目</h3><input id="modal-proj-name" class="input w-full mb-2" placeholder="项目名称" /><textarea id="modal-proj-desc" class="input w-full mb-2" placeholder="描述" rows="2"></textarea><input id="modal-proj-type" class="input w-full mb-2" placeholder="建筑类型" /><div class="flex gap-2 justify-end"><button class="modal-btn modal-btn-secondary" onclick="showTeamDetail('` + teamId + `' )">返回</button><button class="modal-btn modal-btn-primary" onclick="createProject('` + teamId + `' )">创建</button></div>`);
  }
  function createProject(teamId) {
    const name = document.getElementById("modal-proj-name")?.value?.trim() || "";
    if (!name) return;
    const desc = document.getElementById("modal-proj-desc")?.value?.trim() || "";
    const btype = document.getElementById("modal-proj-type")?.value?.trim() || "";
    collabApi("/collab/projects", { method: "POST", body: JSON.stringify({ name, team_id: teamId, description: desc, building_type: btype }) }).then((d) => {
      if (d.status === "success") {
        window.setCurrentTeamId?.(teamId);
        window.setCurrentProjectId?.(String(d.project_id || d.id || ""));
        showTeamDetail(teamId);
      } else {
        showToast$1(collabErrMsg(d), "info");
      }
    });
  }
  function showCreateReviewSessionModal(projectId) {
    setModalBody(`<h3 class="text-lg font-bold mb-4">新建审查会话</h3><input id="modal-rs-name" class="input w-full mb-2" placeholder="名称" /><textarea id="modal-rs-desc" class="input w-full mb-2" placeholder="描述" rows="2"></textarea><div class="flex gap-2 justify-end"><button class="modal-btn modal-btn-secondary" onclick="showProjectDetail('` + projectId + `' )">返回</button><button class="modal-btn modal-btn-primary" onclick="createReviewSession('` + projectId + `' )">创建</button></div>`);
  }
  function createReviewSession(projectId) {
    const name = document.getElementById("modal-rs-name")?.value?.trim() || "";
    if (!name) return;
    const desc = document.getElementById("modal-rs-desc")?.value?.trim() || "";
    collabApi("/collab/review-sessions", { method: "POST", body: JSON.stringify({ project_id: projectId, name, description: desc }) }).then((d) => {
      if (d.status === "success") {
        showProjectDetail(projectId);
      } else {
        showToast$1(collabErrMsg(d), "info");
      }
    });
  }
  function showReviewSessionDetail(sessionId) {
    Promise.all([
      collabApi("/collab/review-sessions/" + sessionId),
      collabApi("/collab/review-sessions/" + sessionId + "/comments"),
      collabApi("/collab/review-sessions/" + sessionId + "/approval-flow")
    ]).then((r) => {
      if (r[0].status !== "success") return;
      const rs = r[0].review_session || {};
      const comments = r[1].comments || [];
      const flow = r[2].approval_flow;
      const statusBadge = '<span class="collab-badge collab-badge-' + String(rs.status) + '">' + String(rs.status) + "</span>";
      let ch = "";
      if (!comments.length) {
        ch = '<p class="text-sm text-gray-400 py-2">暂无评论</p>';
      } else {
        for (const c of comments) {
          const icon = c.comment_type === "issue" ? "⚠️" : c.comment_type === "suggestion" ? "💡" : c.comment_type === "question" ? "❓" : "✅";
          ch += '<div class="comment-box comment-' + String(c.comment_type) + '"><div class="flex justify-between items-start"><span class="font-medium text-sm">' + icon + " " + escHtml$1(String(c.author_name || "")) + '</span><span class="text-xs text-gray-400">' + new Date(Number(c.created_at) * 1e3).toLocaleString() + '</span></div><p class="text-sm mt-1">' + escHtml$1(String(c.content || "")) + "</p>";
          if (c.clause_ref) {
            ch += '<div class="text-xs text-gray-400 mt-1">• 条款: ' + escHtml$1(String(c.clause_ref)) + "</div>";
          }
          if (c.entity_ref) {
            ch += '<div class="text-xs text-gray-400">• 实体: ' + escHtml$1(String(c.entity_ref)) + "</div>";
          }
          ch += "</div>";
        }
      }
      let fh = "";
      if (flow && flow.steps) {
        fh = '<table class="collab-table"><tr><th>序号</th><th>审批人</th><th>状态</th><th>意见</th><th>时间</th></tr>';
        for (const st of flow.steps) {
          const sb = '<span class="collab-badge collab-badge-' + String(st.status) + '">' + String(st.status) + "</span>";
          fh += "<tr><td>" + String(st.order) + "</td><td>" + escHtml$1(String(st.reviewer_name || "")) + "</td><td>" + sb + "</td><td>" + escHtml$1(String(st.comment || "")) + "</td><td>" + (st.acted_at ? new Date(Number(st.acted_at) * 1e3).toLocaleString() : "") + "</td></tr>";
        }
        fh += "</table>";
      } else {
        fh = '<p class="text-sm text-gray-400 py-2">暂无审批流程</p>';
      }
      setModalBody('<h3 class="text-lg font-bold mb-4">审查会话: ' + escHtml$1(String(rs.name || "")) + " " + statusBadge + '</h3><div class="mb-4"><h4 class="font-medium mb-2">评论</h4>' + ch + '</div><div><h4 class="font-medium mb-2">审批流程</h4>' + fh + '</div><div class="flex gap-2 justify-end mt-4"><button class="modal-btn modal-btn-secondary" onclick="closeCollabModal()">关闭</button></div>');
    });
  }
  if (_token) {
    setTimeout(() => {
      collabApi("/collab/users/me", { autoLogout: false }).then((d) => {
        if (d.status === "success") {
          _user = d.user || {};
          localStorage.setItem("baa_collab_user", JSON.stringify(_user));
          updateUserStatus(true);
          const page = document.getElementById("page-collab");
          if (page && page.classList.contains("active")) {
            collabEnterMain();
          } else {
            const mainSec = document.getElementById("collab-main-section");
            const loginSec = document.getElementById("collab-login-section");
            if (mainSec && loginSec) {
              mainSec.style.display = "block";
              loginSec.style.display = "none";
            }
          }
        } else {
          collabLogout();
        }
      }).catch(() => {
        collabLogout();
      });
    }, 500);
  }
  initApiClient({
    apiBase: () => document.getElementById("api-base")?.value || "http://localhost:8000",
    getActiveKeyValue: getActiveKeyValue$1,
    currentTeamId: () => appState.teamId,
    currentProjectId: () => appState.projectId
  });
  initAdminToken();
  const w = window;
  w.formatDate = formatDate;
  w.maskKey = maskKey;
  w.escHtml = escHtml$1;
  w.permissionBadge = permissionBadge;
  w.enabledBadge = enabledBadge;
  w.uid = uid;
  w.mergeDeep = mergeDeep;
  w.showToast = showToast$1;
  w.showSkeleton = showSkeleton;
  w.hideSkeleton = hideSkeleton;
  w.renderSkeletonContainer = renderSkeletonContainer;
  w.renderProgress = renderProgress;
  w.HEADERS = getReviewHeaders;
  w.getHeaders = getHeaders;
  w.adminHeaders = getAdminHeaders;
  w.API_BASE = getApiBase;
  w.apiGet = apiGet;
  w.apiPostJSON = apiPostJSON;
  w.apiPostFile = apiPostFile;
  w.apiFetch = apiFetch;
  w.adminGet = adminGet;
  w.adminPost = adminPost;
  w.adminDelete = adminDelete;
  w.apiPost = async (path, body) => apiPostJSON(path, body);
  w.getCurrentTeamId = () => appState.teamId;
  w.getCurrentProjectId = () => appState.projectId;
  w.setCurrentTeamId = (id) => appState.setTeamId(id || "");
  w.setCurrentProjectId = (id) => appState.setProjectId(id || "");
  w.loadApiBase = () => appState.loadApiBase();
  w.saveApiBase = () => appState.saveApiBase();
  w.getApiKey = () => getActiveKeyValue$1();
  w.getActiveKeyValue = getActiveKeyValue$1;
  w.loadApiKeys = loadKeys;
  w.saveApiKeys = () => {
  };
  w.switchApiKey = switchApiKey;
  w.deleteCurrentApiKey = deleteCurrentApiKey;
  w.addApiKey = addApiKey;
  w.deleteApiKey = deleteApiKey;
  w.copyApiKey = copyApiKey;
  w.populateTokenSelect = populateTokenSelect;
  w.refreshTokenSelect = refreshTokenSelect;
  w.initAdminToken = initAdminToken;
  w.loadAdminKeys = loadAdminKeys;
  w.openCreateKeyModal = openCreateKeyModal;
  w.closeCreateKeyModal = closeCreateKeyModal;
  w.createAdminKey = createAdminKey;
  w.copyCreatedKey = copyCreatedKey;
  w.closeKeyCreatedModal = closeKeyCreatedModal;
  w.showKeyDetail = showKeyDetail;
  w.showDetailRawKey = showDetailRawKey;
  w.copyDetailRawKey = copyDetailRawKey;
  w.copyKeyFromDetail = copyKeyFromDetail;
  w.closeKeyDetailModal = closeKeyDetailModal;
  w.confirmRevokeKey = confirmRevokeKey;
  w.confirmDeleteKey = confirmDeleteKey;
  w.revokeAdminKey = revokeAdminKey;
  w.showDrawingReviewPanel = showDrawingReviewPanel;
  w.switchDrawingTab = switchDrawingTab;
  w.loadReviewContext = loadReviewContext;
  w.onReviewTeamSelect = onReviewTeamSelect;
  w.onReviewProjectSelect = onReviewProjectSelect;
  w.saveParsedDrawings = saveParsedDrawings;
  w.loadParsedDrawings = loadParsedDrawings;
  w.renderDrawingList = renderDrawingList;
  w.toggleDrawingSelect = toggleDrawingSelect;
  w.selectAllDrawings = selectAllDrawings;
  w.deselectAllDrawings = deselectAllDrawings;
  w.updateBatchButton = updateBatchButton;
  w.uploadDrawing = uploadDrawing;
  w.uploadAndReview = uploadAndReview;
  w.batchReview = batchReview;
  w.deleteDrawing = deleteDrawing;
  w.sendToReview = sendToReview;
  w.refreshReviewDrawingSelect = refreshReviewDrawingSelect;
  w.onReviewDrawingSelect = onReviewDrawingSelect;
  w.loadDashboard = loadDashboard;
  w.renderRecentReviews = renderRecentReviews;
  w.renderSpecFreqBars = renderSpecFreqBars;
  w.renderViolationTypeBars = renderViolationTypeBars;
  w.loadReviewResults = loadReviewResults;
  w.fallbackLoadReviewResults = fallbackLoadReviewResults;
  w.refreshCompareDrawingSelect = refreshCompareDrawingSelect;
  w.downloadReviewPdf = downloadReviewPdf;
  w.downloadReviewExport = downloadReviewExport;
  w.downloadReviewJSON = downloadReviewJSON;
  w.loadFeedbackStats = loadFeedbackStats;
  w.loadFeedbacks = loadFeedbacks;
  w.submitFeedback = submitFeedback;
  w._onDiffFileSelect = _onDiffFileSelect;
  w.runDiffComparison = runDiffComparison;
  w.renderDiffResults = renderDiffResults;
  w.renderDiffItemPanel = renderDiffItemPanel;
  w.switchDiffTab = switchDiffTab;
  w.loadDiffVisualization = loadDiffVisualization;
  w.clearDiffResults = clearDiffResults;
  w.onThermalCompTypeChange = onThermalCompTypeChange;
  w.renderThermalThresholds = renderThermalThresholds;
  w.computeThermalK = computeThermalK;
  w.renderThermalViolations = renderThermalViolations;
  w.generateCorrectionSuggestions = generateCorrectionSuggestions;
  w.confirmCorrection = confirmCorrection;
  w.renderStructuralThresholds = renderStructuralThresholds;
  w.onStructuralCompTypeChange = onStructuralCompTypeChange;
  w.computeStructuralCheck = computeStructuralCheck;
  w.renderStructuralViolations = renderStructuralViolations;
  w.renderHistoryList = renderHistoryList;
  w.deleteReviewRecord = deleteReviewRecord;
  w.viewHistoryDetail = viewHistoryDetail;
  w.closeHistoryModal = closeHistoryModal;
  w.clearReviewHistory = clearReviewHistory;
  const _hp = { value: 0 };
  Object.defineProperty(w, "historyPage", {
    get: () => _hp.value,
    set: (v) => {
      _hp.value = v;
    },
    enumerable: true,
    configurable: true
  });
  w.loadSpecs = loadSpecs;
  w.renderSpecList = renderSpecList;
  w.zoomImage = zoomImage;
  w.zoomSet = zoomSet;
  w.zoomReset = zoomReset;
  w.zoomFit = zoomFit;
  w.zoomClose = zoomClose;
  w.runMultiSheetReview = runMultiSheetReview;
  w.switchMultiSheetTab = switchMultiSheetTab;
  w.renderMultiSheetTab = renderMultiSheetTab;
  w.formatTimeAgo = formatTimeAgo;
  w.copyReverseDXF = copyReverseDXF;
  w.generateReverse = generateReverse;
  w.loadFunctions = loadFunctions;
  w.filterFunctions = filterFunctions;
  w.toggleFuncDetail = toggleFuncDetail;
  w.updateFunction = updateFunction;
  w.switchRevTab = switchRevTab;
  w.initMultiRooms = initMultiRooms;
  w.addMultiRoom = addMultiRoom;
  w.generateMultiReverse = generateMultiReverse;
  w.renderLayoutSVG = renderLayoutSVG;
  w.expandReverseSVG = expandReverseSVG;
  w.downloadReverseSVG = downloadReverseSVG;
  w.loadCaseStats = loadCaseStats;
  w.loadCases = loadCases;
  w.renderCaseList = renderCaseList;
  w.renderCasePagination = renderCasePagination;
  w.openCaseDetail = openCaseDetail;
  w.closeCaseDetail = closeCaseDetail;
  w.loadAnalysis = loadAnalysis;
  w.renderOverviewCards = renderOverviewCards;
  w.renderAnalysisTable = renderAnalysisTable;
  w.renderCategoryAnalysis = renderCategoryAnalysis;
  w.renderTrendBars = renderTrendBars;
  w.renderViolationDistBars = renderViolationDistBars;
  w.loadCDItems = loadCDItems;
  w._initAuditItems = _initAuditItems;
  w._loadAuditItemStates = _loadAuditItemStates;
  w.renderAuditButtons = renderAuditButtons;
  w.auditAction = auditAction;
  w.renderAuditStatsBar = renderAuditStatsBar;
  w._loadAuditStats = _loadAuditStats;
  w._refreshAuditPanel = _refreshAuditPanel;
  w._onAuditFilterChange = _onAuditFilterChange;
  w.downloadCorrectionNotice = downloadCorrectionNotice;
  w.MODEL_PARAMS_TABS = MODEL_PARAMS_TABS;
  w.switchModelParamTab = switchModelParamTab;
  w.downloadModelExport = downloadModelExport;
  w.collabErrMsg = collabErrMsg;
  w.collabApi = collabApi;
  w.closeCollabModal = closeCollabModal;
  w.setModalBody = setModalBody;
  w.showCollabLogin = showCollabLogin;
  w.showCollabRegister = showCollabRegister;
  w.collabLogin = collabLogin;
  w.collabRegister = collabRegister;
  w.collabLogout = collabLogout;
  w.collabEnterMain = collabEnterMain;
  w.updateUserStatus = updateUserStatus;
  w.collabRefresh = collabRefresh;
  w.loadCollabStats = loadCollabStats;
  w.loadCollabTeams = loadCollabTeams;
  w.showCreateTeamModal = showCreateTeamModal;
  w.createTeam = createTeam;
  w.showTeamDetail = showTeamDetail;
  w.showProjectDetail = showProjectDetail;
  w.showCreateProjectModal = showCreateProjectModal;
  w.createProject = createProject;
  w.showCreateReviewSessionModal = showCreateReviewSessionModal;
  w.createReviewSession = createReviewSession;
  w.showReviewSessionDetail = showReviewSessionDetail;
  w.testConnection = testConnection;
  w.router = router;
  w.importServerKey = importServerKey;
  w.importSelectedKey = importSelectedKey;
  w.closeImportKeyModal = closeImportKeyModal;
  w.openModal = openModal;
  w.renderFilterBar = renderFilterBar;
  w.renderReviewItem = renderReviewItem;
  w.renderReviewTable = renderReviewTable;
  w.runReview = runReview;
  w.renderViolationOverlay = renderViolationOverlay;
  w.runBatchReviewComponent = runBatchReview;
  console.log("[P123] Vite TS core modules loaded");
  document.addEventListener("DOMContentLoaded", initApp);
})();
//# sourceMappingURL=baa-core-bundle.iife.js.map
