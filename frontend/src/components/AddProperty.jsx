import React, { useState } from "react";
import api from "../services/api";

export default function AddProperty() {
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    await api.post("/api/properties/", { name, location, description });
    setName("");
    setLocation("");
    setDescription("");
  };

  return (
    <div className="card">
      <h3>Add Property</h3>
      <form onSubmit={submit}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" required />
        <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Location" required />
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description" />
        <button type="submit">Create</button>
      </form>
    </div>
  );
}
