import React from "react";
import { ChevronLeft } from "lucide-react";
import { useNavigate } from "react-router-dom";

export default function BackButton() {
  const navigate = useNavigate();

  return (
    <button className="floating-back-btn" onClick={() => navigate(-1)} type="button" aria-label="Go back">
      <ChevronLeft size={18} />
    </button>
  );
}
