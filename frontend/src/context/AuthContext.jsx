import React, { createContext, useState, useEffect } from "react";
import api from "../services/api";
import { getErrorMessage } from "../utils/errors";

export const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);

  const resetExecutiveVisibilityPreference = () => {
    localStorage.setItem("krib-exec-amounts-hidden", "true");
  };

  useEffect(() => {
    const storedUser = localStorage.getItem("user");
    if (storedUser) {
      try {
        setUser(JSON.parse(storedUser));
      } catch {
        localStorage.removeItem("user");
      }
    }
  }, []);

  useEffect(() => {
    const token = localStorage.getItem("access");
    if (!token || user) return;

    let active = true;
    api.get("/api/me/")
      .then((res) => {
        if (!active) return;
        const restoredUser = {
          id: res.data?.id,
          name: res.data?.first_name || res.data?.full_name || res.data?.username,
          email: res.data?.email,
          phone: res.data?.phone_number,
          role: res.data?.role,
          is_staff: Boolean(res.data?.is_staff),
        };
        localStorage.setItem("role", restoredUser.role || "");
        localStorage.setItem("user", JSON.stringify(restoredUser));
        setUser(restoredUser);
      })
      .catch(() => {
        localStorage.removeItem("user");
        localStorage.removeItem("access");
        localStorage.removeItem("refresh");
        localStorage.removeItem("role");
      });

    return () => {
      active = false;
    };
  }, [user]);

  const persistSession = (payload) => {
    if (payload.access) localStorage.setItem("access", payload.access);
    if (payload.refresh) localStorage.setItem("refresh", payload.refresh);
    if (payload.role) localStorage.setItem("role", payload.role);
    resetExecutiveVisibilityPreference();
    if (payload.user) {
      localStorage.setItem("user", JSON.stringify(payload.user));
      setUser(payload.user);
    }
  };

  const login = async (credentials) => {
    const res = await api.post("/api/auth/login/", credentials);
    const userData = {
      id: res.data.user?.id,
      name: res.data.user?.name,
      email: res.data.user?.email,
      phone: res.data.user?.phone,
      role: res.data.role || res.data.user?.role,
      is_staff: Boolean(res.data.user?.is_staff),
    };
    persistSession({
      access: res.data.access,
      refresh: res.data.refresh,
      role: userData.role,
      user: userData,
    });
    return userData;
  };

  const register = async (payload) => {
    try {
      const res = await api.post("/api/auth/register/", payload);
      const userData = {
        id: res.data.user?.id,
        name: res.data.user?.name,
        email: res.data.user?.email,
        phone: res.data.user?.phone,
        role: res.data.role || res.data.user?.role,
        is_staff: Boolean(res.data.user?.is_staff),
      };
      persistSession({
        access: res.data.access,
        refresh: res.data.refresh,
        role: userData.role,
        user: userData,
      });
      return userData;
    } catch (error) {
      throw new Error(getErrorMessage(error, "Unable to create account."));
    }
  };

  const logout = async () => {
    // Best-effort server-side blacklist of the refresh token. We always clear
    // local storage even if the network call fails so the UI is never stuck
    // signed in after the user clicked Sign Out.
    const refresh = localStorage.getItem("refresh");
    if (refresh) {
      try {
        await api.post("/api/auth/logout/", { refresh });
      } catch (err) {
        // network/offline/server-down: ignore; local logout still happens
      }
    }
    localStorage.removeItem("user");
    localStorage.removeItem("access");
    localStorage.removeItem("refresh");
    localStorage.removeItem("role");
    localStorage.removeItem("krib-exec-amounts-hidden");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
