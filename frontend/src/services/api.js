import axios from "axios";

const LOADING_EVENT = "app:network-loading";
let pendingRequestCount = 0;

function emitLoadingState() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent(LOADING_EVENT, {
      detail: { count: pendingRequestCount },
    })
  );
}

function beginRequest() {
  pendingRequestCount += 1;
  emitLoadingState();
}

function endRequest() {
  pendingRequestCount = Math.max(0, pendingRequestCount - 1);
  emitLoadingState();
}

// In development: VITE_API_BASE_URL is not set, so it falls back to localhost.
// In production: docker-compose.prod.yml injects the real URL at build time.
const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: BASE_URL,
});

api.interceptors.request.use(
  (config) => {
    beginRequest();
    const token = localStorage.getItem("access");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    endRequest();
    return Promise.reject(error);
  }
);

api.interceptors.response.use(
  (response) => {
    endRequest();
    return response;
  },
  async (error) => {
    endRequest();
    const originalRequest = error.config;
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