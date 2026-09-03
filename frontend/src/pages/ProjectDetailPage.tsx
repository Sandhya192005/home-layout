import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { FloorPlan, FloorPlanShare, PlanData, Project, Requirement, RequirementInput } from "../api/types";
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
  compound_wall_style: "wall",
  gate_style: "swing",
  floors: 1,
  floor_type: "duplex",
  budget: 3500000,
  vastu_compliant: false,
  wheelchair_accessible: false,
  additional_rooms: [],
  other_requirements: null,
};

const PRESETS: { name: string; description: string; values: Partial<RequirementInput> }[] = [
  {
    name: "Compact 2BHK",
    description: "35×25 ft, 1 floor, 2 bed / 2 bath",
    values: { plot_length: 35, plot_width: 25, bedrooms: 2, bathrooms: 2, floors: 1, floor_type: "duplex", cars: 1, two_wheelers: 1, has_veranda: true, has_foyer: false, wheelchair_accessible: false },
  },
  {
    name: "3BHK Duplex",
    description: "50×35 ft, 2 floors, single household",
    values: { plot_length: 50, plot_width: 35, bedrooms: 3, bathrooms: 3, floors: 2, floor_type: "duplex", cars: 2, two_wheelers: 1, has_veranda: true, has_foyer: false, wheelchair_accessible: false },
  },
  {
    name: "Independent 2-unit home",
    description: "55×40 ft, 2 floors, separate house each floor",
    values: { plot_length: 55, plot_width: 40, bedrooms: 4, bathrooms: 4, floors: 2, floor_type: "independent", cars: 2, two_wheelers: 2, has_veranda: true, has_foyer: true, wheelchair_accessible: false },
  },
  {
    name: "Accessible bungalow",
    description: "45×35 ft, 1 floor, wheelchair accessible",
    values: { plot_length: 45, plot_width: 35, bedrooms: 2, bathrooms: 2, floors: 1, floor_type: "duplex", cars: 1, two_wheelers: 0, has_veranda: false, has_foyer: true, wheelchair_accessible: true },
  },
];

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const pid = Number(projectId);

  const [project, setProject] = useState<Project | null>(null);
  const [form, setForm] = useState<RequirementInput>(DEFAULT_REQUIREMENT);
  const [latestRequirement, setLatestRequirement] = useState<Requirement | null>(null);
  const [floorPlan, setFloorPlan] = useState<FloorPlan | null>(null);
  const [floorPlanVersions, setFloorPlanVersions] = useState<FloorPlan[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [deletingVersionId, setDeletingVersionId] = useState<number | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);
  const [deletingAllVersions, setDeletingAllVersions] = useState(false);
  const [pendingDeleteAll, setPendingDeleteAll] = useState(false);
  const [share, setShare] = useState<FloorPlanShare | null>(null);
  const [shareBusy, setShareBusy] = useState(false);
  const [shareCopied, setShareCopied] = useState(false);

  const [compareMode, setCompareMode] = useState(false);
  const [compareLeftId, setCompareLeftId] = useState<number | null>(null);
  const [compareRightId, setCompareRightId] = useState<number | null>(null);

  // --- undo/redo over manual edits (furniture, room/parking resize,
  // attached-bathroom, replace-room) -- every one of those funnels its
  // result through applyPlanUpdate below, so this stays a single stack of
  // whole plan_data snapshots rather than a bespoke inverse per edit type.
  const MAX_UNDO_HISTORY = 20;
  const [undoStack, setUndoStack] = useState<PlanData[]>([]);
  const [redoStack, setRedoStack] = useState<PlanData[]>([]);
  const [undoRedoBusy, setUndoRedoBusy] = useState(false);
  const [undoRedoError, setUndoRedoError] = useState<string | null>(null);

  // A different floor_plan row (version switch, regenerate, initial load)
  // starts a fresh undo/redo history -- it isn't meaningful across rows.
  useEffect(() => {
    setUndoStack([]);
    setRedoStack([]);
    setUndoRedoError(null);
  }, [floorPlan?.id]);

  function applyPlanUpdate(newPlanData: PlanData) {
    if (!floorPlan) return;
    setUndoStack((stack) => [...stack.slice(-(MAX_UNDO_HISTORY - 1)), floorPlan.plan_data]);
    setRedoStack([]);
    setUndoRedoError(null);
    setFloorPlan((fp) => (fp ? { ...fp, plan_data: newPlanData } : fp));
  }

  async function undo() {
    if (!floorPlan || undoStack.length === 0 || undoRedoBusy) return;
    const target = undoStack[undoStack.length - 1];
    setUndoRedoBusy(true);
    setUndoRedoError(null);
    try {
      const restored = await api.restorePlanData(pid, floorPlan.id, target);
      setRedoStack((stack) => [...stack, floorPlan.plan_data]);
      setUndoStack((stack) => stack.slice(0, -1));
      setFloorPlan(restored);
    } catch (err) {
      setUndoRedoError(err instanceof ApiError ? err.message : "Could not undo");
    } finally {
      setUndoRedoBusy(false);
    }
  }

  async function redo() {
    if (!floorPlan || redoStack.length === 0 || undoRedoBusy) return;
    const target = redoStack[redoStack.length - 1];
    setUndoRedoBusy(true);
    setUndoRedoError(null);
    try {
      const restored = await api.restorePlanData(pid, floorPlan.id, target);
      setUndoStack((stack) => [...stack, floorPlan.plan_data]);
      setRedoStack((stack) => stack.slice(0, -1));
      setFloorPlan(restored);
    } catch (err) {
      setUndoRedoError(err instanceof ApiError ? err.message : "Could not redo");
    } finally {
      setUndoRedoBusy(false);
    }
  }

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
    api.listFloorPlans(pid).then(setFloorPlanVersions).catch(() => {});
  }, [pid]);

  function applyPreset(preset: (typeof PRESETS)[number]) {
    setForm((f) => ({ ...f, ...preset.values }));
  }

  useEffect(() => {
    if (pendingDeleteId === null) return;
    const t = setTimeout(() => setPendingDeleteId(null), 3000);
    return () => clearTimeout(t);
  }, [pendingDeleteId]);

  useEffect(() => {
    if (!pendingDeleteAll) return;
    const t = setTimeout(() => setPendingDeleteAll(false), 3000);
    return () => clearTimeout(t);
  }, [pendingDeleteAll]);

  useEffect(() => {
    setShareCopied(false);
    if (!floorPlan) {
      setShare(null);
      return;
    }
    api
      .getShare(pid, floorPlan.id)
      .then(setShare)
      .catch(() => setShare(null));
  }, [pid, floorPlan]);

  async function handleCreateShare() {
    if (!floorPlan || shareBusy) return;
    setShareBusy(true);
    try {
      const result = await api.createShare(pid, floorPlan.id);
      setShare(result);
    } catch {
      setError("Could not create share link");
    } finally {
      setShareBusy(false);
    }
  }

  async function handleRevokeShare() {
    if (!floorPlan || shareBusy) return;
    setShareBusy(true);
    try {
      await api.revokeShare(pid, floorPlan.id);
      setShare(null);
      setShareCopied(false);
    } catch {
      setError("Could not revoke share link");
    } finally {
      setShareBusy(false);
    }
  }

  async function handleCopyShareLink() {
    if (!share) return;
    const url = `${window.location.origin}/share/${share.token}`;
    try {
      await navigator.clipboard.writeText(url);
      setShareCopied(true);
    } catch {
      /* clipboard permission denied -- link is still shown in the input for manual copy */
    }
  }

  async function selectVersion(floorPlanId: number) {
    try {
      const plan = await api.getFloorPlan(pid, floorPlanId);
      setFloorPlan(plan);
    } catch {
      setError("Could not load that version");
    }
  }

  function toggleCompareMode() {
    setCompareMode((on) => {
      if (!on && floorPlanVersions.length >= 2) {
        // floorPlanVersions is newest-first -- default to comparing the two most recent versions
        setCompareLeftId((prev) => prev ?? floorPlanVersions[1].id);
        setCompareRightId((prev) => prev ?? floorPlanVersions[0].id);
      }
      return !on;
    });
  }

  function roomCount(plan: FloorPlan): number {
    return plan.plan_data.floors.reduce((sum, f) => sum + f.rooms.length, 0);
  }

  function formatDiff(delta: number, digits = 0): string {
    const rounded = Number(delta.toFixed(digits));
    if (rounded === 0) return "no change";
    return rounded > 0 ? `+${rounded.toLocaleString()}` : rounded.toLocaleString();
  }

  function handleDeleteVersionClick(floorPlanId: number) {
    if (pendingDeleteId === floorPlanId) {
      setPendingDeleteId(null);
      deleteVersion(floorPlanId);
    } else {
      setPendingDeleteId(floorPlanId);
    }
  }

  async function deleteVersion(floorPlanId: number) {
    if (deletingVersionId) return;
    setDeletingVersionId(floorPlanId);
    try {
      await api.revokeShare(pid, floorPlanId).catch(() => {});
      await api.deleteFloorPlan(pid, floorPlanId);
      const remaining = await api.listFloorPlans(pid);
      setFloorPlanVersions(remaining);
      if (floorPlan?.id === floorPlanId) {
        setFloorPlan(remaining.length > 0 ? await api.getFloorPlan(pid, remaining[0].id) : null);
      }
    } catch {
      setError("Could not delete that version");
    } finally {
      setDeletingVersionId(null);
    }
  }

  function handleDeleteAllVersionsClick() {
    if (pendingDeleteAll) {
      setPendingDeleteAll(false);
      deleteAllVersions();
    } else {
      setPendingDeleteAll(true);
    }
  }

  async function deleteAllVersions() {
    if (deletingAllVersions || floorPlanVersions.length === 0) return;
    setDeletingAllVersions(true);
    try {
      for (const v of floorPlanVersions) {
        await api.revokeShare(pid, v.id).catch(() => {});
        await api.deleteFloorPlan(pid, v.id);
      }
      setFloorPlanVersions([]);
      setFloorPlan(null);
      setCompareMode(false);
      // next "Generate" now starts back at version 1, since no active floor plan remains for it to build on
    } catch {
      setError("Could not delete all versions -- some may remain");
      setFloorPlanVersions(await api.listFloorPlans(pid).catch(() => []));
    } finally {
      setDeletingAllVersions(false);
    }
  }

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
      api.listFloorPlans(pid).then(setFloorPlanVersions).catch(() => {});
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

          <div className="field">
            <label>Quick start</label>
            <div className="preset-row">
              {PRESETS.map((preset) => (
                <button
                  key={preset.name}
                  type="button"
                  className="preset-chip"
                  title={preset.description}
                  onClick={() => applyPreset(preset)}
                >
                  {preset.name}
                </button>
              ))}
            </div>
          </div>

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
            {form.floors > 1 && (
              <div className="field">
                <label htmlFor="floor_type">Multi-floor style</label>
                <select
                  id="floor_type"
                  value={form.floor_type}
                  onChange={(e) => update("floor_type", e.target.value as RequirementInput["floor_type"])}
                >
                  <option value="duplex">Duplex (single house, internal staircase)</option>
                  <option value="independent">Independent floors (separate house per floor)</option>
                </select>
              </div>
            )}
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

          <div className="field-row">
            <div className="field">
              <label htmlFor="compound_wall_style">Compound boundary</label>
              <select
                id="compound_wall_style"
                value={form.compound_wall_style}
                onChange={(e) => update("compound_wall_style", e.target.value as RequirementInput["compound_wall_style"])}
              >
                <option value="none">None (open setback)</option>
                <option value="wall">Compound wall</option>
                <option value="fence">Fence</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="gate_style">Gate style</label>
              <select
                id="gate_style"
                value={form.gate_style}
                onChange={(e) => update("gate_style", e.target.value as RequirementInput["gate_style"])}
              >
                <option value="swing">Swing gate</option>
                <option value="sliding">Sliding gate</option>
              </select>
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
          {floorPlanVersions.length > 0 && (
            <div className="version-row card">
              <span className="muted">Versions</span>
              {floorPlanVersions.map((v) => (
                <span key={v.id} className="version-chip-group">
                  <button
                    type="button"
                    className={`version-chip ${floorPlan?.id === v.id ? "version-chip-active" : ""}`}
                    onClick={() => selectVersion(v.id)}
                  >
                    v{v.version}
                  </button>
                  <button
                    type="button"
                    className={`version-chip-delete ${pendingDeleteId === v.id ? "version-chip-delete-confirm" : ""}`}
                    title={pendingDeleteId === v.id ? "Click again to confirm delete" : `Delete version ${v.version}`}
                    disabled={deletingVersionId === v.id}
                    onClick={() => handleDeleteVersionClick(v.id)}
                  >
                    {pendingDeleteId === v.id ? "confirm?" : "×"}
                  </button>
                </span>
              ))}
              <span className="version-row-actions">
                {floorPlanVersions.length > 1 && (
                  <button type="button" className="btn btn-secondary version-compare-toggle" onClick={toggleCompareMode}>
                    {compareMode ? "Close compare" : "Compare versions"}
                  </button>
                )}
                <button
                  type="button"
                  className="btn btn-danger version-delete-all"
                  disabled={deletingAllVersions}
                  title="Delete every version so the next generate starts back at version 1"
                  onClick={handleDeleteAllVersionsClick}
                >
                  {deletingAllVersions ? "Deleting…" : pendingDeleteAll ? "Click again to confirm" : "Delete all versions"}
                </button>
              </span>
            </div>
          )}

          {compareMode && floorPlanVersions.length > 1 && (
            <div className="compare-panel card">
              <div className="compare-picker-row">
                <label>
                  <span className="muted">Compare</span>
                  <select value={compareLeftId ?? ""} onChange={(e) => setCompareLeftId(Number(e.target.value))}>
                    {floorPlanVersions.map((v) => (
                      <option key={v.id} value={v.id}>
                        v{v.version} &middot; {Math.round(v.total_built_up_area).toLocaleString()} sq ft
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span className="muted">with</span>
                  <select value={compareRightId ?? ""} onChange={(e) => setCompareRightId(Number(e.target.value))}>
                    {floorPlanVersions.map((v) => (
                      <option key={v.id} value={v.id}>
                        v{v.version} &middot; {Math.round(v.total_built_up_area).toLocaleString()} sq ft
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              {(() => {
                const left = floorPlanVersions.find((v) => v.id === compareLeftId);
                const right = floorPlanVersions.find((v) => v.id === compareRightId);
                if (!left || !right) return <p className="muted">Pick two versions to compare.</p>;
                return (
                  <>
                    <div className="compare-diff-row">
                      <div>
                        <span className="muted">Built-up area</span>{" "}
                        <strong className="mono">{formatDiff(right.total_built_up_area - left.total_built_up_area)} sq ft</strong>
                      </div>
                      <div>
                        <span className="muted">Estimated cost</span>{" "}
                        <strong className="mono">₹{formatDiff(right.estimated_cost - left.estimated_cost)}</strong>
                      </div>
                      <div>
                        <span className="muted">Rooms</span>{" "}
                        <strong className="mono">{formatDiff(roomCount(right) - roomCount(left))}</strong>
                      </div>
                      <div>
                        <span className="muted">Floors</span>{" "}
                        <strong className="mono">{formatDiff(right.plan_data.floors.length - left.plan_data.floors.length)}</strong>
                      </div>
                    </div>
                    <div className="compare-grid">
                      <div>
                        <div className="compare-col-label">v{left.version}</div>
                        <FloorPlanViewer plan={left.plan_data} />
                      </div>
                      <div>
                        <div className="compare-col-label">v{right.version}</div>
                        <FloorPlanViewer plan={right.plan_data} />
                      </div>
                    </div>
                  </>
                );
              })()}
            </div>
          )}

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

              <div className="share-row card">
                {share ? (
                  <>
                    <span className="muted">Read-only link</span>
                    <input
                      className="share-link-input mono"
                      readOnly
                      value={`${window.location.origin}/share/${share.token}`}
                      onFocus={(e) => e.currentTarget.select()}
                    />
                    <button type="button" className="btn btn-secondary" onClick={handleCopyShareLink}>
                      {shareCopied ? "Copied!" : "Copy link"}
                    </button>
                    <button type="button" className="btn btn-danger" onClick={handleRevokeShare} disabled={shareBusy}>
                      Revoke
                    </button>
                  </>
                ) : (
                  <button type="button" className="btn btn-secondary" onClick={handleCreateShare} disabled={shareBusy}>
                    {shareBusy ? "Creating…" : "Create shareable link"}
                  </button>
                )}
              </div>

              {(floorPlan.plan_data.meta.boq || floorPlan.plan_data.meta.construction_timeline || floorPlan.plan_data.meta.far) && (
                <details className="estimate-details card">
                  <summary>Materials &amp; timeline estimate</summary>

                  {floorPlan.plan_data.meta.far && (
                    <p className={`far-line ${floorPlan.plan_data.meta.far.exceeds_typical_limit ? "far-over" : ""}`}>
                      Floor-area-ratio (FAR): <strong>{floorPlan.plan_data.meta.far.far}</strong>{" "}
                      (typical residential limit ~{floorPlan.plan_data.meta.far.max_far})
                      {floorPlan.plan_data.meta.far.exceeds_typical_limit && " — confirm local FAR/FSI norms"}
                    </p>
                  )}

                  {floorPlan.plan_data.meta.boq && (
                    <div className="estimate-block">
                      <h4>Bill of quantities (approximate)</h4>
                      <div className="estimate-grid">
                        <div><span className="muted">Cement</span> <strong>{floorPlan.plan_data.meta.boq.cement_bags} bags</strong></div>
                        <div><span className="muted">Steel</span> <strong>{floorPlan.plan_data.meta.boq.steel_kg.toLocaleString()} kg</strong></div>
                        <div><span className="muted">Bricks</span> <strong>{floorPlan.plan_data.meta.boq.bricks.toLocaleString()}</strong></div>
                        <div><span className="muted">Sand</span> <strong>{floorPlan.plan_data.meta.boq.sand_cft.toLocaleString()} cu ft</strong></div>
                        <div><span className="muted">Aggregate</span> <strong>{floorPlan.plan_data.meta.boq.aggregate_cft.toLocaleString()} cu ft</strong></div>
                        <div><span className="muted">Paint</span> <strong>{floorPlan.plan_data.meta.boq.paint_liters} L</strong></div>
                      </div>
                    </div>
                  )}

                  {floorPlan.plan_data.meta.construction_timeline && (
                    <div className="estimate-block">
                      <h4>
                        Construction timeline &mdash; ~{floorPlan.plan_data.meta.construction_timeline.total_months} months
                        ({floorPlan.plan_data.meta.construction_timeline.total_weeks} weeks)
                      </h4>
                      <div className="estimate-grid">
                        {Object.entries(floorPlan.plan_data.meta.construction_timeline.phases_weeks).map(([phase, weeks]) => (
                          <div key={phase}>
                            <span className="muted">{phase.replace(/_/g, " ")}</span> <strong>{weeks} wk</strong>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <p className="estimate-disclaimer">
                    Rule-of-thumb estimates from built-up area only — not a substitute for a structural engineer's BOQ or a contractor's schedule.
                  </p>
                </details>
              )}

              <FloorPlanViewer
                plan={floorPlan.plan_data}
                projectId={pid}
                floorPlanId={floorPlan.id}
                onFurnitureSaved={applyPlanUpdate}
                onUndo={undo}
                onRedo={redo}
                canUndo={undoStack.length > 0}
                canRedo={redoStack.length > 0}
                undoRedoBusy={undoRedoBusy}
                undoRedoError={undoRedoError}
              />
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
