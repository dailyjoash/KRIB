import React, { createContext, useCallback, useEffect, useMemo, useRef, useState } from "react";
import api, { clearAuthStorage, setApiAccessToken } from "../services/api";
import { getErrorMessage } from "../utils/errors";

export const AuthContext = createContext(null);

const emptyAuthState = {
  user: null,
  role: "",
  accessToken: "",
  refreshToken: "",
};

const normalizeUser = (data, fallbackRole = "") => ({
  id: data?.id,
  name: data?.name || data?.first_name || data?.full_name || data?.username,
  email: data?.email,
  phone: data?.phone || data?.phone_number,
  role: fallbackRole || data?.role || "",
  is_staff: Boolean(data?.is_staff),
});

const readStoredUser = () => {
  const storedUser = localStorage.getItem("user");
  if (!storedUser) return null;

  try {
    return JSON.parse(storedUser);
  } catch {
    localStorage.removeItem("user");
    sessionStorage.removeItem("user");
    return null;
  }
};

const readStoredAuth = () => {
  const accessToken = localStorage.getItem("access") || "";
  const refreshToken = localStorage.getItem("refresh") || "";
  const role = localStorage.getItem("role") || "";
  const storedUser = accessToken && role ? readStoredUser() : null;
  const user = storedUser ? { ...storedUser, role: storedUser.role || role } : null;

  return {
    user,
    role,
    accessToken,
    refreshToken,
  };
};

export function AuthProvider({ children }) {
  const authChangeRef = useRef(0);
  const [authState, setAuthState] = useState(readStoredAuth);
  const [authReady, setAuthReady] = useState(() => {
    const storedAuth = readStoredAuth();
    return !storedAuth.accessToken || Boolean(storedAuth.user);
  });

  const resetExecutiveVisibilityPreference = () => {
    localStorage.setItem("krib-exec-amounts-hidden", "true");
  };

  const clearSession = useCallback(() => {
    authChangeRef.current += 1;
    clearAuthStorage();
    setAuthState(emptyAuthState);
    setAuthReady(true);
  }, []);

  const persistSession = useCallback((payload) => {
    const nextUser = payload.user || null;
    const nextRole = payload.role || nextUser?.role || "";
    const nextAccessToken = payload.access || "";
    const nextRefreshToken = payload.refresh || "";

    authChangeRef.current += 1;

    if (nextAccessToken) {
      localStorage.setItem("access", nextAccessToken);
      setApiAccessToken(nextAccessToken);
    } else {
      localStorage.removeItem("access");
      setApiAccessToken(null);
    }

    if (nextRefreshToken) {
      localStorage.setItem("refresh", nextRefreshToken);
    } else {
      localStorage.removeItem("refresh");
    }

    if (nextRole) {
      localStorage.setItem("role", nextRole);
    } else {
      localStorage.removeItem("role");
    }

    resetExecutiveVisibilityPreference();

    if (nextUser) {
      localStorage.setItem("user", JSON.stringify({ ...nextUser, role: nextRole }));
    } else {
      localStorage.removeItem("user");
    }

    setAuthState({
      user: nextUser ? { ...nextUser, role: nextRole } : null,
      role: nextRole,
      accessToken: nextAccessToken,
      refreshToken: nextRefreshToken,
    });
    setAuthReady(true);
  }, []);

  useEffect(() => {
    const storedAuth = readStoredAuth();

    if (!storedAuth.accessToken || !storedAuth.role) {
      clearSession();
      return undefined;
    }

    setApiAccessToken(storedAuth.accessToken);

    if (storedAuth.user) {
      setAuthReady(true);
      return undefined;
    }

    let active = true;
    const authRun = authChangeRef.current;
    setAuthReady(false);

    api.get("/api/me/")
      .then((res) => {
        if (!active || authRun !== authChangeRef.current) return;
        const restoredUser = normalizeUser(res.data, res.data?.role || storedAuth.role);
        persistSession({
          access: storedAuth.accessToken,
          refresh: storedAuth.refreshToken,
          role: restoredUser.role,
          user: restoredUser,
        });
      })
      .catch(() => {
        if (active && authRun === authChangeRef.current) {
          clearSession();
        }
      });

    return () => {
      active = false;
    };
  }, [clearSession, persistSession]);

  const login = useCallback(async (credentials) => {
    const res = await api.post("/api/auth/login/", credentials);
    const userData = normalizeUser(res.data?.user, res.data?.role || res.data?.user?.role);
    persistSession({
      access: res.data?.access,
      refresh: res.data?.refresh,
      role: userData.role,
      user: userData,
    });
    return userData;
  }, [persistSession]);

  const register = useCallback(async (payload) => {
    try {
      const res = await api.post("/api/auth/register/", payload);
      const userData = normalizeUser(res.data?.user, res.data?.role || res.data?.user?.role);
      persistSession({
        access: res.data?.access,
        refresh: res.data?.refresh,
        role: userData.role,
        user: userData,
      });
      return userData;
    } catch (error) {
      throw new Error(getErrorMessage(error, "Unable to create account."));
    }
  }, [persistSession]);

  const logout = useCallback(() => {
    const refresh = authState.refreshToken || localStorage.getItem("refresh");
    const access = authState.accessToken || localStorage.getItem("access");

    clearSession();

    if (!refresh) {
      return Promise.resolve();
    }

    return api.post(
      "/api/auth/logout/",
      { refresh },
      access ? { headers: { Authorization: `Bearer ${access}` } } : undefined
    ).catch(() => undefined);
  }, [authState.accessToken, authState.refreshToken, clearSession]);

  const isAuthenticated = Boolean(authState.accessToken && authState.role && authState.user);

  const contextValue = useMemo(
    () => ({
      user: authState.user,
      role: authState.role,
      accessToken: authState.accessToken,
      refreshToken: authState.refreshToken,
      isAuthenticated,
      authReady,
      login,
      register,
      logout,
      clearSession,
    }),
    [authReady, authState, clearSession, isAuthenticated, login, logout, register]
  );

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
}
