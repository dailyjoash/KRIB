import React, { useContext, useMemo } from "react";
import { AuthContext } from "../context/AuthContext";

const getGreeting = (date = new Date()) => {
  const hour = date.getHours();
  if (hour >= 5 && hour <= 11) return "Good morning";
  if (hour >= 12 && hour <= 16) return "Good afternoon";
  return "Good evening";
};

const getStoredName = () => {
  try {
    const stored = localStorage.getItem("user");
    if (!stored) return null;
    const parsed = JSON.parse(stored);
    return parsed?.username || null;
  } catch {
    return null;
  }
};

export default function Greeting() {
  const { user } = useContext(AuthContext);

  const name = useMemo(() => user?.username || getStoredName() || "there", [user?.username]);

  return <>{`${getGreeting()}, ${name}`}</>;
}
