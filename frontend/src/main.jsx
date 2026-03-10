import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import App from "./App";

import "./styles.css";

const savedTheme = localStorage.getItem("theme") || "light";
if (savedTheme === "light") {
  document.documentElement.classList.add("theme-light");
} else {
  document.documentElement.classList.remove("theme-light");
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </AuthProvider>
  </React.StrictMode>
);
