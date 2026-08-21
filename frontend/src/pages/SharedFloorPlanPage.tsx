import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { PublicFloorPlan } from "../api/types";
import FloorPlanViewer from "../components/FloorPlanViewer";
import "./project-detail.css";

export default function SharedFloorPlanPage() {
  const { token } = useParams<{ token: string }>();
  const [plan, setPlan] = useState<PublicFloorPlan | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api
      .getPublicFloorPlan(token)
      .then(setPlan)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load this shared link"));
  }, [token]);

  if (error) {
    return (
      <div className="project-detail">
        <div className="error-banner">{error}</div>
      </div>
    );
  }

  if (!plan) {
    return (
      <div className="project-detail">
        <p className="muted">Loading…</p>
      </div>
    );
  }

  return (
    <div className="project-detail">
      <div className="project-detail-header">
        <h1>{plan.project_name}</h1>
        <p className="muted">Shared read-only floor plan &middot; version {plan.version}</p>
      </div>

      <div className="plan-meta card">
        <div>
          <span className="muted">Version</span> <strong className="mono">{plan.version}</strong>
        </div>
        <div>
          <span className="muted">Built-up area</span>{" "}
          <strong className="mono">{Math.round(plan.total_built_up_area).toLocaleString()} sq ft</strong>
        </div>
        <div>
          <span className="muted">Estimated cost</span>{" "}
          <strong className="mono">₹{Math.round(plan.estimated_cost).toLocaleString()}</strong>
        </div>
        <div>
          <span className="muted">Status</span> <span className={`status-chip status-${plan.status}`}>{plan.status}</span>
        </div>
      </div>

      <FloorPlanViewer plan={plan.plan_data} />
    </div>
  );
}
