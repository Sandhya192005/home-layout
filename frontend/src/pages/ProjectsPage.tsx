import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { Project } from "../api/types";
import "./projects.css";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  function load() {
    api
      .listProjects()
      .then(setProjects)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load projects"));
  }

  useEffect(load, []);

  async function handleDelete(p: Project) {
    if (!window.confirm(`Delete "${p.name}"? This cannot be undone.`)) return;
    setDeletingId(p.id);
    setError(null);
    try {
      await api.deleteProject(p.id);
      setProjects((prev) => prev?.filter((x) => x.id !== p.id) ?? prev);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete project");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      await api.createProject({ name, description: description || null });
      setName("");
      setDescription("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create project");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="projects-page">
      <div className="projects-header">
        <div>
          <h1>Your projects</h1>
          <p className="muted">Each project holds a plot's requirements and its generated floor plans.</p>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <form className="card new-project-form" onSubmit={handleCreate}>
        <h2 style={{ fontSize: "1.1rem" }}>New project</h2>
        <div className="field-row">
          <div className="field">
            <label htmlFor="name">Project name</label>
            <input id="name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="My New Home" />
          </div>
          <div className="field">
            <label htmlFor="description">Description (optional)</label>
            <input
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="3BHK independent house"
            />
          </div>
        </div>
        <button className="btn btn-primary" type="submit" disabled={creating}>
          {creating ? "Creating…" : "Create project"}
        </button>
      </form>

      {projects === null ? (
        <p className="muted">Loading…</p>
      ) : projects.length === 0 ? (
        <p className="muted">No projects yet — create your first one above.</p>
      ) : (
        <ul className="project-list">
          {projects.map((p) => (
            <li key={p.id} className="card project-item">
              <Link to={`/projects/${p.id}`} className="project-item-link">
                <div>
                  <div className="project-item-name">{p.name}</div>
                  {p.description && <div className="muted">{p.description}</div>}
                </div>
                <span className={`status-chip status-${p.status}`}>{p.status}</span>
              </Link>
              <button
                type="button"
                className="btn btn-danger project-item-delete"
                disabled={deletingId === p.id}
                onClick={() => handleDelete(p)}
              >
                {deletingId === p.id ? "Deleting…" : "Delete"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
