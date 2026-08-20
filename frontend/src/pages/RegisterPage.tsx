import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api/client";
import "./auth.css";

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register(email, fullName, password);
      navigate("/projects");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not register");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <form className="card auth-card" onSubmit={handleSubmit}>
        <h1>Create an account</h1>
        <p className="muted">Start designing your home layout.</p>
        {error && <div className="error-banner">{error}</div>}
        <div className="field">
          <label htmlFor="full_name">Full name</label>
          <input id="full_name" required value={fullName} onChange={(e) => setFullName(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            required
            minLength={8}
            maxLength={72}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <span className="muted" style={{ fontSize: "0.78rem" }}>
            At least 8 characters.
          </span>
        </div>
        <button className="btn btn-primary" type="submit" disabled={submitting}>
          {submitting ? "Creating account…" : "Create account"}
        </button>
        <p className="muted">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </form>
    </div>
  );
}
