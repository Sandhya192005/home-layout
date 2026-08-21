import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { FloorPlan, Project, Requirement, RequirementInput } from "../api/types";
import { ADDITIONAL_ROOM_TYPES } from "../api/types";
import FloorPlanViewer from "../components/FloorPlanViewer";
import "./project-detail.css";

const DEFAULT_REQUIREMENT: RequirementInput = {
  plot_length: 50,
  plot_width: 35,
  facing: "north",
  family_members: 4,
  bedrooms: 2,
  bathrooms: 2,
  has_living_room: true,
  has_dining_room: true,
  has_pooja_room: false,
  has_study_room: false,
  has_utility_room: true,
  has_veranda: true,
  has_foyer: false,
  balconies: 0,
  cars: 1,
  two_wheelers: 1,
  floors: 1,
  budget: 3500000,
  vastu_compliant: false,
  wheelchair_accessible: false,
  additional_rooms: [],
  other_requirements: null,
};

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);

  const [project, setProject] = useState<Project | null>(null);
  const [form, setForm] = useState<RequirementInput>(DEFAULT_REQUIREMENT);
  const [latestRequirement, setLatestRequirement] = useState<Requirement | null>(null);
  const [floorPlan, setFloorPlan] = useState<FloorPlan | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    api.getProject(pid).then(setProject).catch(() => setError("Could not load project"));
    api
      .latestRequirement(pid)
      .then((req) => {
        setLatestRequirement(req);
        setForm(req);
      })
      .catch(() => {
        /* no requirement submitted yet */
      });
    api.latestFloorPlan(pid).then(setFloorPlan).catch(() => {});
  }, [pid]);

  function update<K extends keyof RequirementInput>(key: K, value: RequirementInput[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function toggleAdditionalRoom(room: string) {
    setForm((f) => {
      const has = f.additional_rooms.includes(room as never);
      return {
        ...f,
        additional_rooms: has
          ? f.additional_rooms.filter((r) => r !== room)
          : [...f.additional_rooms, room as (typeof ADDITIONAL_ROOM_TYPES)[number]],
      };
    });
  }

  async function handleGenerate() {
    setError(null);
    setGenerating(true);
    setWarnings([]);
    try {
      const req = await api.submitRequirement(pid, form);
      setLatestRequirement(req);
      const result = await api.generatePlan(pid, req.id);
      setFloorPlan(result.floor_plan);
      setWarnings(result.warnings);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not generate floor plan");
    } finally {
      setGenerating(false);
    }
  }

  if (!project) {
    return error ? <div className="error-banner">{error}</div> : <p className="muted">Loading…</p>;
  }

  return (
    <div className="project-detail">
      <Link to="/projects" className="back-link">
        &larr; Projects
      </Link>
      <div className="project-detail-header">
        <h1>{project.name}</h1>
        {project.description && <p className="muted">{project.description}</p>}
      </div>

      <div className="pd-layout">
        <form
          className="card requirement-form"
          onSubmit={(e) => {
            e.preventDefault();
            handleGenerate();
          }}
        >
          <h2>Requirements</h2>

          <div className="field-row">
            <div className="field">
              <label htmlFor="plot_length">Plot length (ft, N-S)</label>
              <input
                id="plot_length"
                type="number"
                min={1}
                max={1000}
                step="0.1"
                required
                value={form.plot_length}
                onChange={(e) => update("plot_length", Number(e.target.value))}
              />
            </div>
            <div className="field">
              <label htmlFor="plot_width">Plot width (ft, E-W)</label>
              <input
                id="plot_width"
                type="number"
                min={1}
                max={1000}
                step="0.1"
                required
                value={form.plot_width}
                onChange={(e) => update("plot_width", Number(e.target.value))}
              />
            </div>
            <div className="field">
              <label htmlFor="facing">Facing</label>
              <select id="facing" value={form.facing} onChange={(e) => update("facing", e.target.value as RequirementInput["facing"])}>
                <option value="north">North</option>
                <option value="south">South</option>
                <option value="east">East</option>
                <option value="west">West</option>
              </select>
            </div>
          </div>

          <div className="field-row">
            <div className="field">
              <label htmlFor="family_members">Family members</label>
              <input
                id="family_members"
                type="number"
                min={1}
                max={30}
                required
                value={form.family_members}
                onChange={(e) => update("family_members", Number(e.target.value))}
              />
            </div>
            <div className="field">
              <label htmlFor="bedrooms">Bedrooms</label>
              <input
                id="bedrooms"
                type="number"
                min={1}
                max={12}
                required
                value={form.bedrooms}
                onChange={(e) => update("bedrooms", Number(e.target.value))}
              />
            </div>
            <div className="field">
              <label htmlFor="bathrooms">Bathrooms</label>
              <input
                id="bathrooms"
                type="number"
                min={1}
                max={12}
                required
                value={form.bathrooms}
                onChange={(e) => update("bathrooms", Number(e.target.value))}
              />
            </div>
            <div className="field">
              <label htmlFor="floors">Floors</label>
              <input
                id="floors"
                type="number"
                min={1}
                max={5}
                required
                value={form.floors}
                onChange={(e) => update("floors", Number(e.target.value))}
              />
            </div>
          </div>

          <div className="checkbox-grid">
            <label className="checkbox-row">
              <input type="checkbox" checked={form.has_living_room} onChange={(e) => update("has_living_room", e.target.checked)} />
              Living room
            </label>
            <label className="checkbox-row">
              <input type="checkbox" checked={form.has_dining_room} onChange={(e) => update("has_dining_room", e.target.checked)} />
              Dining room
            </label>
            <label className="checkbox-row">
              <input type="checkbox" checked={form.has_pooja_room} onChange={(e) => update("has_pooja_room", e.target.checked)} />
              Pooja room
            </label>
            <label className="checkbox-row">
              <input type="checkbox" checked={form.has_study_room} onChange={(e) => update("has_study_room", e.target.checked)} />
              Study room
            </label>
            <label className="checkbox-row">
              <input type="checkbox" checked={form.has_utility_room} onChange={(e) => update("has_utility_room", e.target.checked)} />
              Utility room
            </label>
            <label className="checkbox-row">
              <input type="checkbox" checked={form.vastu_compliant} onChange={(e) => update("vastu_compliant", e.target.checked)} />
              Vastu compliant
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={form.has_veranda}
                onChange={(e) => update("has_veranda", e.target.checked)}
              />
              Add veranda (covered porch entrance)
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={form.has_foyer}
                onChange={(e) => update("has_foyer", e.target.checked)}
              />
              Add foyer (enclosed hall entrance)
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={form.wheelchair_accessible}
                onChange={(e) => update("wheelchair_accessible", e.target.checked)}
              />
              Wheelchair accessible
            </label>
          </div>

          <div className="field-row">
            <div className="field">
              <label htmlFor="balconies">Balconies</label>
              <input
                id="balconies"
                type="number"
                min={0}
                max={12}
                value={form.balconies}
                onChange={(e) => update("balconies", Number(e.target.value))}
              />
            </div>
            <div className="field">
              <label htmlFor="cars">Cars</label>
              <input id="cars" type="number" min={0} max={10} value={form.cars} onChange={(e) => update("cars", Number(e.target.value))} />
            </div>
            <div className="field">
              <label htmlFor="two_wheelers">Two-wheelers</label>
              <input
                id="two_wheelers"
                type="number"
                min={0}
                max={10}
                value={form.two_wheelers}
                onChange={(e) => update("two_wheelers", Number(e.target.value))}
              />
            </div>
            <div className="field">
              <label htmlFor="budget">Budget (INR)</label>
              <input
                id="budget"
                type="number"
                min={0}
                step="10000"
                value={form.budget}
                onChange={(e) => update("budget", Number(e.target.value))}
              />
            </div>
          </div>

          <div className="field">
            <label>Additional rooms</label>
            <div className="checkbox-grid">
              {ADDITIONAL_ROOM_TYPES.map((room) => (
                <label className="checkbox-row" key={room}>
                  <input
                    type="checkbox"
                    checked={form.additional_rooms.includes(room)}
                    onChange={() => toggleAdditionalRoom(room)}
                  />
                  {room.replace(/_/g, " ")}
                </label>
              ))}
            </div>
          </div>

          <div className="field">
            <label htmlFor="other_requirements">Other requirements (optional)</label>
            <textarea
              id="other_requirements"
              rows={2}
              value={form.other_requirements ?? ""}
              onChange={(e) => update("other_requirements", e.target.value || null)}
            />
          </div>

          {error && <div className="error-banner">{error}</div>}

          <button className="btn btn-primary" type="submit" disabled={generating}>
            {generating ? "Generating…" : latestRequirement ? "Regenerate floor plan" : "Generate floor plan"}
          </button>
        </form>

        <div className="pd-results">
          {warnings.length > 0 && (
            <div className="warning-banner card">
              {warnings.map((w, i) => (
                <p key={i}>{w}</p>
              ))}
            </div>
          )}

          {floorPlan ? (
            <>
              <div className="plan-meta card">
                <div>
                  <span className="muted">Version</span> <strong className="mono">{floorPlan.version}</strong>
                </div>
                <div>
                  <span className="muted">Built-up area</span>{" "}
                  <strong className="mono">{Math.round(floorPlan.total_built_up_area).toLocaleString()} sq ft</strong>
                </div>
                <div>
                  <span className="muted">Estimated cost</span>{" "}
                  <strong className="mono">₹{Math.round(floorPlan.estimated_cost).toLocaleString()}</strong>
                </div>
                <div>
                  <span className="muted">Status</span> <span className={`status-chip status-${floorPlan.status}`}>{floorPlan.status}</span>
                </div>
              </div>

              <FloorPlanViewer plan={floorPlan.plan_data} />
            </>
          ) : (
            <div className="card empty-state">
              <p className="muted">No floor plan generated yet. Fill in the requirements and click Generate.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
