import React, { useContext, useEffect, useMemo, useState } from "react";
import { AuthContext } from "../context/AuthContext";
import api from "../services/api";

const getPeriodGreeting = () => {
  const hour = new Date().getHours();
  if (hour >= 5 && hour <= 11) return "Good morning";
  if (hour >= 12 && hour <= 16) return "Good afternoon";
  return "Good evening";
};

export default function Greeting() {
  const { user } = useContext(AuthContext);
  const [name, setName] = useState(user?.username || "there");

  useEffect(() => {
    const stored = localStorage.getItem("user");
    if (user?.username) {
      setName(user.username);
      return;
    }

    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        if (parsed?.username) {
          setName(parsed.username);
          return;
        }
      } catch {
        // no-op
      }
    }

    const access = localStorage.getItem("access");
    if (!access) return;

    api.get("/api/me/")
      .then((res) => {
        if (res.data?.username) setName(res.data.username);
      })
      .catch(() => {
        setName("there");
      });
  }, [user?.username]);

  const text = useMemo(() => `${getPeriodGreeting()}, ${name}`, [name]);

  return <>{text}</>;
}
