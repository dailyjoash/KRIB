import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "",
  timeout: 60000,
});

const AUTH_STORAGE_KEYS = ["user", "access", "refresh", "role", "krib-exec-amounts-hidden"];

export const setApiAccessToken = (token) => {
  if (token) {
    api.defaults.headers.common.Authorization = `Bearer ${token}`;
    return;
  }

  delete api.defaults.headers.common.Authorization;
};

export const clearAuthStorage = () => {
  AUTH_STORAGE_KEYS.forEach((key) => {
    localStorage.removeItem(key);
    sessionStorage.removeItem(key);
  });
  setApiAccessToken(null);
};

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access");
  config.headers = config.headers || {};
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  } else if (!config.headers.Authorization) {
    delete config.headers.Authorization;
  }
  return config;
});

let refreshPromise = null;

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const refreshToken = localStorage.getItem("refresh");
    const isAuthRefreshCall = originalRequest?.url?.includes("/api/token/refresh/");

    if (error.response?.status !== 401 || !refreshToken || originalRequest?._retry || isAuthRefreshCall) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    try {
      if (!refreshPromise) {
        refreshPromise = axios.post(`${import.meta.env.VITE_API_URL || ""}/api/token/refresh/`, { refresh: refreshToken });
      }
      const refreshResponse = await refreshPromise;
      const nextAccess = refreshResponse.data.access;
      localStorage.setItem("access", nextAccess);
      setApiAccessToken(nextAccess);
      originalRequest.headers.Authorization = `Bearer ${nextAccess}`;
      return api(originalRequest);
    } catch (refreshError) {
      clearAuthStorage();
      if (window.location.pathname !== "/login") {
        window.location.replace("/login");
      }
      return Promise.reject(refreshError);
    } finally {
      refreshPromise = null;
    }
  }
);

export default api;
