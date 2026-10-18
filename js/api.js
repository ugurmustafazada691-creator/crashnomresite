/**
 * Crash Number Bot Frontend API helper
 * Backend: http://127.0.0.1:8000
 */
const API_BASE = localStorage.getItem("API_BASE") || "http://127.0.0.1:8000";

function getTokens() {
  return {
    access: localStorage.getItem("access_token"),
    refresh: localStorage.getItem("refresh_token"),
  };
}

function setTokens(access, refresh) {
  if (access) localStorage.setItem("access_token", access);
  if (refresh) localStorage.setItem("refresh_token", refresh);
}

function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("user");
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const { access } = getTokens();
  if (access) headers["Authorization"] = `Bearer ${access}`;

  let res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  // Auto refresh once on 401
  if (res.status === 401 && getTokens().refresh && !options._retried) {
    const r = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: getTokens().refresh }),
    });
    if (r.ok) {
      const data = await r.json();
      setTokens(data.access_token, data.refresh_token);
      return api(path, { ...options, _retried: true });
    }
    clearTokens();
    window.location.href = "login.html";
    throw new Error("Sessiya bitdi");
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data.detail || (typeof data.detail === "string" ? data.detail : "Xəta");
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

async function login(login, password) {
  const data = await api("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ login, password }),
  });
  setTokens(data.access_token, data.refresh_token);
  return data;
}

async function register(username, email, password, referral_code, accept_terms) {
  const data = await api("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({
      username,
      email,
      password,
      referral_code: referral_code || null,
      accept_terms: !!accept_terms,
    }),
  });
  setTokens(data.access_token, data.refresh_token);
  return data;
}

async function me() {
  return api("/api/auth/me");
}

async function getBalance() {
  return api("/api/balance/");
}

window.KingAPI = { api, login, register, me, getBalance, setTokens, clearTokens, getTokens, API_BASE };
