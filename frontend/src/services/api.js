import axios from "axios";

const LOADING_EVENT = "app:network-loading";
let pendingRequestCount = 0;

function emitLoadingState() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent(LOADING_EVENT, { detail: { count: pendingRequestCount } })
  );
}

function beginRequest() { pendingRequestCount += 1; emitLoadingState(); }
function endRequest()   { pendingRequestCount = Math.max(0, pendingRequestCount - 1); emitLoadingState(); }

// ── DRF pagination unwrapper ──────────────────────────────────────────────────
// DRF wraps list responses as { count, next, previous, results: [...] }
// when pagination is enabled. This detects that shape and unwraps it so
// every service call sees a plain array — no component needs to handle both.
//
// Single-object responses (dashboard, challan, user profile etc.) pass through
// unchanged because they won't have both "results" and "count" keys together.
function unwrapIfPaginated(response) {
  const d = response.data;
  if (
    d !== null &&
    typeof d === "object" &&
    !Array.isArray(d) &&
    "results" in d &&
    "count"   in d &&
    Array.isArray(d.results)
  ) {
    response.data = d.results;
  }
  return response;
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const api = axios.create({ baseURL: BASE_URL });

// ── Request interceptor ───────────────────────────────────────────────────────
api.interceptors.request.use(
  (config) => {
    beginRequest();
    const token = localStorage.getItem("access");
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
  },
  (error) => { endRequest(); return Promise.reject(error); }
);

// ── Response interceptor ──────────────────────────────────────────────────────
api.interceptors.response.use(
  (response) => {
    endRequest();
    return unwrapIfPaginated(response); // unwraps once, transparently, for all callers
  },
  async (error) => {
    endRequest();
    const originalRequest = error.config;

    // Auto-refresh expired access token
    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      originalRequest._retry = true;
      const refresh = localStorage.getItem("refresh");
      if (refresh) {
        try {
          const res = await axios.post(`${BASE_URL}/api/token/refresh/`, { refresh });
          const newAccess = res.data.access;
          localStorage.setItem("access", newAccess);
          originalRequest.headers = originalRequest.headers || {};
          originalRequest.headers.Authorization = `Bearer ${newAccess}`;
          return api(originalRequest);
        } catch {
          localStorage.clear();
          window.location.href = "/login";
        }
      } else {
        localStorage.clear();
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export default api;