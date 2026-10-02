import axios from "axios";
import { queryClient, clearQueryCache } from "./queryClient";

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
          clearQueryCache();
          window.location.href = "/login";
        }
      } else {
        localStorage.clear();
          clearQueryCache();
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

// ── TanStack Query cache for GETs ────────────────────────────────────────────
// Coming back to a page within 2 min reuses the cached response. Any successful
// write marks everything stale so the next visit refetches. { noCache: true }
// on a call always hits the API.
const NO_CACHE = [
  /\/api\/user\/?$/, /\/api\/notifications\//, /\/api\/student\/(live-location|bus-tracking)\//,
  /\/api\/incidents\/approved\//, /\/api\/crime-risk\//, /\/challan\/?$/,
  /\/api\/admin\/live-fleet\//, /\/api\/driver\//,
];
// Writes that don't change admin/student data (pings, read receipts).
const NO_INVALIDATE = [/\/api\/notifications\//, /\/api\/driver\/location\//, /\/api\/bus-location\//];

const rawGet = api.get.bind(api);
api.get = (url, config = {}) => {
  const { noCache, ...cfg } = config;
  if (noCache || NO_CACHE.some((rx) => rx.test(url))) return rawGet(url, cfg);
  return queryClient
    .fetchQuery({
      queryKey: ["api", url, cfg.params ?? null, cfg.responseType ?? null],
      queryFn: () => rawGet(url, cfg).then(({ data, status, headers }) => ({ data, status, headers })),
    })
    .then((res) => ({ ...res, data: structuredClone(res.data) })); // pages can't mutate the cache
};

api.interceptors.response.use((response) => {
  const method = (response.config?.method || "").toLowerCase();
  const url = response.config?.url || "";
  if (method !== "get") {
    if (/\/api\/(token|login)\/?$/.test(url)) clearQueryCache();
    else if (!NO_INVALIDATE.some((rx) => rx.test(url))) queryClient.invalidateQueries({ queryKey: ["api"] });
  }
  return response;
});

export default api;