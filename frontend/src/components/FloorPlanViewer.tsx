import { useMemo, useState } from "react";
import type { FloorData, PlanData, RoomData } from "../api/types";
import { furnitureIconMarkup } from "./furnitureIcons";
import { bikeIconMarkup, carIconMarkup, treeIconMarkup } from "./siteIcons";
import "./floor-plan-viewer.css";

const CATEGORY: Record<string, "social" | "sleep" | "wet"> = {
  living_room: "social",
  dining_room: "social",
  foyer: "social",
  master_bedroom: "sleep",
  bedroom: "sleep",
  guest_room: "sleep",
  kitchen: "wet",
  bathroom: "wet",
  accessible_bathroom: "wet",
  utility: "wet",
};
const CATEGORY_LABEL: Record<string, string> = {
  social: "Social / living",
  sleep: "Sleeping",
  wet: "Kitchen / wet area",
  other: "Other",
};
function categoryOf(type: string) {
  return CATEGORY[type] ?? "other";
}

const fmt = (n: number, d = 1) => n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
const fmt0 = (n: number) => Math.round(n).toLocaleString();

function niceScaleLength(target: number): number {
  const pow = Math.pow(10, Math.floor(Math.log10(target)));
  for (const m of [1, 2, 5, 10]) {
    if (m * pow >= target) return m * pow;
  }
  return 10 * pow;
}

function angleOf(cx: number, cy: number, px: number, py: number) {
  return Math.atan2(py - cy, px - cx);
}
function normalizeDelta(a: number) {
  let d = a;
  while (d <= -Math.PI) d += 2 * Math.PI;
  while (d > Math.PI) d -= 2 * Math.PI;
  return d;
}

/** Builds the inner SVG markup (grid, parking, rooms, walls, windows, door
 * swings, north arrow, scale bar) for one floor. Ported from the standalone
 * drafting-table viewer; kept as string-built markup since it's proven and
 * the geometry math doesn't benefit from being re-expressed as JSX. */
function buildFloorSvg(floor: FloorData, plotLength: number, plotWidth: number): { svg: string; viewBox: string } {
  const roomsById = Object.fromEntries(floor.rooms.map((r) => [r.id, r]));
  const isGroundFloor = floor.floor_number === 0;
  const plot = { x: 0, y: 0, w: plotWidth, l: plotLength };

  let minX = Math.min(floor.outline.x, isGroundFloor ? plot.x : Infinity);
  let minY = Math.min(floor.outline.y, isGroundFloor ? plot.y : Infinity);
  let maxX = Math.max(floor.outline.x + floor.outline.width, isGroundFloor ? plot.x + plot.w : -Infinity);
  let maxY = Math.max(floor.outline.y + floor.outline.length, isGroundFloor ? plot.y + plot.l : -Infinity);
  if (floor.parking) {
    minX = Math.min(minX, floor.parking.x);
    minY = Math.min(minY, floor.parking.y);
    maxX = Math.max(maxX, floor.parking.x + floor.parking.width);
    maxY = Math.max(maxY, floor.parking.y + floor.parking.length);
  }
  const spanX = maxX - minX;
  const spanY = maxY - minY;
  const unit = Math.max(spanX, spanY) / 100;
  const margin = unit * 11;
  const vbX = minX - margin;
  const vbY = minY - margin - unit * 4;
  const vbW = spanX + margin * 2;
  const vbH = spanY + margin * 2 + unit * 4;

  let svg = "";

  // Garden/site fill: the full plot, so the setback gaps around the building
  // read as landscaping rather than blank paper. Only meaningful at ground
  // level -- upper floors don't have a yard.
  if (isGroundFloor) {
    svg += `<rect x="${plot.x}" y="${plot.y}" width="${plot.w}" height="${plot.l}" fill="var(--garden)" stroke="var(--line-soft)" stroke-width="${unit * 0.06}" stroke-dasharray="${unit * 0.3} ${unit * 0.25}" />`;

    // scatter trees around the perimeter gap, skipping anywhere that falls
    // inside the building outline or the parking rect
    const insideBuilding = (x: number, y: number) =>
      x > floor.outline.x + unit && x < floor.outline.x + floor.outline.width - unit &&
      y > floor.outline.y + unit && y < floor.outline.y + floor.outline.length - unit;
    const insideParking = (x: number, y: number) =>
      !!floor.parking &&
      x > floor.parking.x - unit && x < floor.parking.x + floor.parking.width + unit &&
      y > floor.parking.y - unit && y < floor.parking.y + floor.parking.length + unit;

    const treeSize = Math.max(unit * 3, Math.min(unit * 5, spanX / 14));
    // Inset the ring by half a tree width (plus a little breathing room) so
    // tree CENTERS land inside the plot rather than exactly on its boundary
    // -- placing them on the boundary and then rejecting anything too close
    // to the boundary was a self-defeating combination that produced zero
    // trees on every plot.
    const pad = treeSize * 0.6;
    const innerW = plot.w - pad * 2;
    const innerL = plot.l - pad * 2;
    if (innerW > 0 && innerL > 0) {
      const cols = Math.max(2, Math.round(innerW / (treeSize * 3.5)));
      const rows = Math.max(2, Math.round(innerL / (treeSize * 3.5)));
      let seed = 0;
      for (let ix = 0; ix <= cols; ix++) {
        for (let iy = 0; iy <= rows; iy++) {
          const onEdge = ix === 0 || iy === 0 || ix === cols || iy === rows;
          if (!onEdge) continue; // only ring the perimeter, not scatter everywhere
          const tx = plot.x + pad + (ix / cols) * innerW;
          const ty = plot.y + pad + (iy / rows) * innerL;
          if (insideBuilding(tx, ty) || insideParking(tx, ty)) continue;
          seed++;
          svg += `<g transform="translate(${tx - treeSize / 2} ${ty - treeSize / 2}) scale(${treeSize} ${treeSize})" stroke-width="${unit * 0.06}">${treeIconMarkup(seed)}</g>`;
        }
      }
    }
  }

  const gridStep = niceScaleLength(spanX / 10);
  let grid = `<g stroke="var(--paper-line)" stroke-width="${unit * 0.05}">`;
  for (let gx = Math.ceil(vbX / gridStep) * gridStep; gx < vbX + vbW; gx += gridStep) {
    grid += `<line x1="${gx}" y1="${vbY}" x2="${gx}" y2="${vbY + vbH}" />`;
  }
  for (let gy = Math.ceil(vbY / gridStep) * gridStep; gy < vbY + vbH; gy += gridStep) {
    grid += `<line x1="${vbX}" y1="${gy}" x2="${vbX + vbW}" y2="${gy}" />`;
  }
  grid += `</g>`;
  svg += grid;

  if (floor.parking) {
    const p = floor.parking;
    svg += `<rect x="${p.x}" y="${p.y}" width="${p.width}" height="${p.length}" fill="var(--surface)" stroke="var(--warm)" stroke-width="${unit * 0.1}" stroke-dasharray="${unit * 0.5} ${unit * 0.3}" />`;

    const horiz = p.width >= p.length; // cars lined up side by side along the wider axis
    const totalSlots = p.capacity_cars + p.capacity_two_wheelers;
    if (totalSlots > 0) {
      const along = horiz ? p.width : p.length;
      const cross = horiz ? p.length : p.width;
      const slotSize = along / totalSlots;
      let idx = 0;
      const placeIcon = (markup: string, marginFrac: number) => {
        const center = idx * slotSize + slotSize / 2;
        const size = Math.min(slotSize, cross) * (1 - marginFrac * 2);
        const cx = horiz ? p.x + center : p.x + cross / 2;
        const cy = horiz ? p.y + cross / 2 : p.y + center;
        svg += `<g transform="translate(${cx - size / 2} ${cy - size / 2}) scale(${size} ${size})" stroke-width="${unit * 0.06}">${markup}</g>`;
        idx++;
      };
      for (let i = 0; i < p.capacity_cars; i++) placeIcon(carIconMarkup(i + 1), 0.08);
      for (let i = 0; i < p.capacity_two_wheelers; i++) placeIcon(bikeIconMarkup(), 0.18);
    }
    svg += `<text x="${p.x + p.width / 2}" y="${p.y - unit * 0.6}" text-anchor="middle" class="room-dim" font-size="${unit * 1.4}">PARKING</text>`;
  }

  if (floor.ramp) {
    const rp = floor.ramp;
    svg += `<defs><pattern id="rampHatch" width="${unit * 0.9}" height="${unit * 0.9}" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
      <line x1="0" y1="0" x2="0" y2="${unit * 0.9}" stroke="var(--wood-dark)" stroke-width="${unit * 0.18}" />
    </pattern></defs>`;
    svg += `<rect x="${rp.x}" y="${rp.y}" width="${rp.width}" height="${rp.length}" fill="url(#rampHatch)" stroke="var(--wood-dark)" stroke-width="${unit * 0.08}" />`;
    const rlx = rp.x + rp.width / 2;
    const rly = rp.side === "north" ? rp.y - unit * 0.5 : rp.y + rp.length + unit * 1.3;
    svg += `<text x="${rlx}" y="${rly}" text-anchor="middle" class="room-dim" font-size="${unit * 1.1}">RAMP</text>`;
  }

  if (floor.main_gate) {
    const g = floor.main_gate;
    const horiz = g.side === "north" || g.side === "south";
    const x1 = g.x, y1 = g.y;
    const x2 = horiz ? g.x + g.width : g.x;
    const y2 = horiz ? g.y : g.y + g.width;
    const labelDX = horiz ? 0 : g.side === "west" ? -unit * 2.4 : unit * 2.4;
    const labelDY = horiz ? (g.side === "north" ? -unit * 1.6 : unit * 2.6) : 0;
    svg += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="var(--warm)" stroke-width="${unit * 0.35}" />`;
    svg += `<circle cx="${x1}" cy="${y1}" r="${unit * 0.35}" fill="var(--wall)" />`;
    svg += `<circle cx="${x2}" cy="${y2}" r="${unit * 0.35}" fill="var(--wall)" />`;
    svg += `<text x="${(x1 + x2) / 2 + labelDX}" y="${(y1 + y2) / 2 + labelDY}" text-anchor="middle" class="room-dim" font-size="${unit * 1.1}">MAIN GATE</text>`;
  }

  for (const r of floor.rooms) {
    const cat = categoryOf(r.type);
    const cx = r.x + r.width / 2;
    const cy = r.y + r.length / 2;
    const labelSize = Math.max(unit * 1.55, Math.min(unit * 2.6, r.width / 9));
    const dimSize = labelSize * 0.62;
    const halo = `stroke="var(--room-${cat})" stroke-width="${labelSize * 0.5}" stroke-linejoin="round" paint-order="stroke"`;
    svg += `<g class="room-shape" data-room="${r.id}">`;
    svg += `<rect class="room-outline" data-room="${r.id}" x="${r.x}" y="${r.y}" width="${r.width}" height="${r.length}" fill="var(--room-${cat})" stroke-width="${unit * 0.12}" />`;
    if (r.type === "staircase") {
      svg += `<g transform="translate(${r.x} ${r.y}) scale(${r.width} ${r.length})" stroke-width="${unit * 0.04}">${furnitureIconMarkup("staircase")}</g>`;
    }
    for (const it of r.furniture ?? []) {
      svg += `<g transform="translate(${it.x} ${it.y}) scale(${it.w} ${it.l})" stroke-width="${unit * 0.05}">${furnitureIconMarkup(it.type)}</g>`;
    }
    svg += `<text x="${cx}" y="${cy - labelSize * 0.35}" text-anchor="middle" class="room-label" font-size="${labelSize}" ${halo}>${r.label.toUpperCase()}</text>`;
    svg += `<text x="${cx}" y="${cy + dimSize * 1.15}" text-anchor="middle" class="room-dim" font-size="${dimSize}" ${halo}>(${fmt(r.width)}&#8242; &times; ${fmt(r.length)}&#8242;)</text>`;
    if (r.below_min_size) {
      svg += `<circle class="flag-dot" cx="${r.x + r.width - unit * 1.4}" cy="${r.y + unit * 1.4}" r="${unit * 0.7}" />`;
    }
    svg += `</g>`;
  }

  let walls = `<g stroke-linecap="square">`;
  for (const w of floor.walls) {
    const isExterior = w.type === "exterior";
    const width = isExterior ? unit * 0.55 : unit * 0.26;
    walls += `<line x1="${w.x1}" y1="${w.y1}" x2="${w.x2}" y2="${w.y2}" stroke="var(--wall)" stroke-width="${width}" />`;
    // a thinner lighter stripe down the middle reads as a brick-course texture
    walls += `<line x1="${w.x1}" y1="${w.y1}" x2="${w.x2}" y2="${w.y2}" stroke="var(--wall-light)" stroke-width="${width * 0.32}" />`;
  }
  walls += `</g>`;
  svg += walls;

  for (const win of floor.windows ?? []) {
    const horiz = win.wall === "north" || win.wall === "south";
    const half = win.width / 2;
    const tick = unit * 0.9;
    if (horiz) {
      svg += `<g stroke="var(--accent)" stroke-width="${unit * 0.1}">
        <line x1="${win.center_x - half}" y1="${win.center_y - tick / 2}" x2="${win.center_x - half}" y2="${win.center_y + tick / 2}" />
        <line x1="${win.center_x + half}" y1="${win.center_y - tick / 2}" x2="${win.center_x + half}" y2="${win.center_y + tick / 2}" />
        <line x1="${win.center_x - half}" y1="${win.center_y}" x2="${win.center_x + half}" y2="${win.center_y}" />
      </g>`;
    } else {
      svg += `<g stroke="var(--accent)" stroke-width="${unit * 0.1}">
        <line x1="${win.center_x - tick / 2}" y1="${win.center_y - half}" x2="${win.center_x + tick / 2}" y2="${win.center_y - half}" />
        <line x1="${win.center_x - tick / 2}" y1="${win.center_y + half}" x2="${win.center_x + tick / 2}" y2="${win.center_y + half}" />
        <line x1="${win.center_x}" y1="${win.center_y - half}" x2="${win.center_x}" y2="${win.center_y + half}" />
      </g>`;
    }
  }

  const findWallFor = (door: FloorData["doors"][number]) => {
    if (door.type === "main_entrance") {
      return floor.walls.find((w) => w.type === "exterior" && w.side === door.wall);
    }
    return floor.walls.find(
      (w) => w.type === "interior" && w.between && w.between.includes(door.room_id) && w.between.includes(door.connects_to ?? "")
    );
  };
  for (const door of floor.doors ?? []) {
    const wall = findWallFor(door);
    if (!wall) continue;
    const horiz = Math.abs(wall.y1 - wall.y2) < 1e-6;
    const half = door.width / 2;
    const hinge = horiz ? { x: door.center_x - half, y: door.center_y } : { x: door.center_x, y: door.center_y - half };
    const gapEnd = horiz ? { x: door.center_x + half, y: door.center_y } : { x: door.center_x, y: door.center_y + half };
    const room = roomsById[door.room_id];
    const roomCx = room ? room.x + room.width / 2 : hinge.x;
    const roomCy = room ? room.y + room.length / 2 : hinge.y;
    let leafTip: { x: number; y: number };
    if (horiz) {
      const sign = roomCy > hinge.y ? 1 : -1;
      leafTip = { x: hinge.x, y: hinge.y + sign * door.width };
    } else {
      const sign = roomCx > hinge.x ? 1 : -1;
      leafTip = { x: hinge.x + sign * door.width, y: hinge.y };
    }
    const a1 = angleOf(hinge.x, hinge.y, leafTip.x, leafTip.y);
    const a2 = angleOf(hinge.x, hinge.y, gapEnd.x, gapEnd.y);
    const sweep = normalizeDelta(a2 - a1) > 0 ? 1 : 0;
    const strokeW = unit * 0.08;
    svg += `<g stroke="var(--ink-soft)" stroke-width="${strokeW}" fill="none">
      <line x1="${hinge.x}" y1="${hinge.y}" x2="${leafTip.x}" y2="${leafTip.y}" />
      <path d="M ${leafTip.x} ${leafTip.y} A ${door.width} ${door.width} 0 0 ${sweep} ${gapEnd.x} ${gapEnd.y}" stroke-dasharray="${unit * 0.4} ${unit * 0.3}" />
    </g>`;
    svg += `<line x1="${hinge.x}" y1="${hinge.y}" x2="${gapEnd.x}" y2="${gapEnd.y}" stroke="var(--paper)" stroke-width="${unit * 0.5}" />`;
  }

  const naX = vbX + vbW - margin * 0.55;
  const naY = vbY + margin * 0.55;
  const naSize = unit * 3.2;
  svg += `<g transform="translate(${naX} ${naY})">
    <circle r="${naSize}" fill="var(--surface)" stroke="var(--line-soft)" stroke-width="${unit * 0.08}" />
    <path d="M 0 ${-naSize * 0.7} L ${naSize * 0.32} ${naSize * 0.45} L 0 ${naSize * 0.18} L ${-naSize * 0.32} ${naSize * 0.45} Z" fill="var(--ink)" />
    <text y="${-naSize * 0.95}" text-anchor="middle" class="room-dim" font-size="${naSize * 0.55}" fill="var(--ink)">N</text>
  </g>`;

  const barLen = niceScaleLength(spanX / 6);
  const barX = vbX + margin * 0.6;
  const barY = vbY + vbH - margin * 0.35;
  svg += `<g transform="translate(${barX} ${barY})" stroke="var(--ink)" stroke-width="${unit * 0.09}">
    <line x1="0" y1="0" x2="${barLen}" y2="0" />
    <line x1="0" y1="${-unit * 0.4}" x2="0" y2="${unit * 0.4}" />
    <line x1="${barLen}" y1="${-unit * 0.4}" x2="${barLen}" y2="${unit * 0.4}" />
    <text x="${barLen / 2}" y="${unit * 1.9}" text-anchor="middle" class="room-dim" font-size="${unit * 1.3}" stroke="none" fill="var(--ink-soft)">${barLen} FT</text>
  </g>`;

  return { svg, viewBox: `${vbX} ${vbY} ${vbW} ${vbH}` };
}

export default function FloorPlanViewer({ plan }: { plan: PlanData }) {
  const [activeFloorIdx, setActiveFloorIdx] = useState(0);
  const [activeRoomId, setActiveRoomId] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; room: RoomData } | null>(null);

  const floor = plan.floors[activeFloorIdx];
  const { svg, viewBox } = useMemo(
    () => buildFloorSvg(floor, plan.meta.plot_length, plan.meta.plot_width),
    [floor, plan.meta.plot_length, plan.meta.plot_width]
  );
  const rows = useMemo(() => [...floor.rooms].sort((a, b) => b.area - a.area), [floor]);
  const totalArea = useMemo(() => rows.reduce((s, r) => s + r.area, 0), [rows]);

  function findRoomIdFromEvent(e: React.MouseEvent): string | null {
    const target = e.target as SVGElement;
    const el = target.closest("[data-room]");
    return el?.getAttribute("data-room") ?? null;
  }

  function handleMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    const roomId = findRoomIdFromEvent(e);
    if (!roomId) {
      setTooltip(null);
      return;
    }
    const room = floor.rooms.find((r) => r.id === roomId);
    if (!room) return;
    const rect = e.currentTarget.getBoundingClientRect();
    setTooltip({ x: e.clientX - rect.left, y: e.clientY - rect.top, room });
  }

  function handleClick(e: React.MouseEvent<HTMLDivElement>) {
    const roomId = findRoomIdFromEvent(e);
    setActiveRoomId((prev) => (prev === roomId ? null : roomId));
  }

  return (
    <div className="floor-plan-viewer">
      {plan.floors.length > 1 && (
        <div className="floor-tabs">
          {plan.floors.map((f, i) => (
            <button
              key={f.floor_number}
              className="floor-tab"
              aria-selected={i === activeFloorIdx}
              onClick={() => {
                setActiveFloorIdx(i);
                setActiveRoomId(null);
              }}
            >
              {f.label}
            </button>
          ))}
        </div>
      )}

      <div className="fpv-layout">
        <div className="drawing-panel card">
          <div className="drawing-panel-head">
            <span className="drawing-panel-title">{floor.label} Plan</span>
            <span className="drawing-panel-plot">
              Plot: {fmt0(plan.meta.plot_width)}&#8242; &times; {fmt0(plan.meta.plot_length)}&#8242;
            </span>
            <span className="drawing-panel-floor">
              {plan.meta.facing.charAt(0).toUpperCase() + plan.meta.facing.slice(1)} facing
            </span>
          </div>
          <div
            className="drawing-svg-wrap"
            onMouseMove={handleMouseMove}
            onMouseLeave={() => setTooltip(null)}
            onClick={handleClick}
          >
            <svg
              viewBox={viewBox}
              className={activeRoomId ? `has-active` : ""}
              dangerouslySetInnerHTML={{ __html: svg }}
            />
            <style>{`.room-outline[data-room="${activeRoomId}"] { stroke: var(--accent) !important; }`}</style>
            {tooltip && (
              <div
                className="fpv-tooltip"
                style={{ left: tooltip.x, top: tooltip.y }}
              >
                <b>{tooltip.room.label}</b>
                <br />
                Zone {tooltip.room.zone} &middot; {fmt(tooltip.room.width)}&#8242; &times; {fmt(tooltip.room.length)}&#8242; &middot; {fmt0(tooltip.room.area)} sq ft
                {tooltip.room.below_min_size && (
                  <>
                    <br />
                    Below recommended minimum
                  </>
                )}
              </div>
            )}
          </div>
          <div className="legend">
            <span className="legend-title">Key:</span>
            {(["social", "sleep", "wet", "other"] as const).map((c) => (
              <div key={c} className="legend-item">
                <span className="legend-swatch" style={{ background: `var(--room-${c})` }} />
                {CATEGORY_LABEL[c]}
              </div>
            ))}
            <div className="legend-item">
              <span className="legend-swatch" style={{ background: "var(--warm-soft)", borderColor: "var(--warm)" }} />
              Parking
            </div>
            <div className="legend-item">
              <span className="legend-swatch" style={{ background: "var(--garden)", borderColor: "var(--line-soft)" }} />
              Garden / setback
            </div>
            <div className="legend-item">
              <svg className="legend-line" viewBox="0 0 24 10">
                <line x1="1" y1="5" x2="23" y2="5" stroke="var(--wall)" strokeWidth="5" />
                <line x1="1" y1="5" x2="23" y2="5" stroke="var(--wall-light)" strokeWidth="1.6" />
              </svg>
              Exterior wall (brick)
            </div>
            <div className="legend-item">
              <svg className="legend-line" viewBox="0 0 24 10">
                <line x1="1" y1="5" x2="23" y2="5" stroke="var(--wall)" strokeWidth="2.5" />
                <line x1="1" y1="5" x2="23" y2="5" stroke="var(--wall-light)" strokeWidth="0.8" />
              </svg>
              Interior wall
            </div>
            <div className="legend-item">
              <svg className="legend-line" viewBox="0 0 24 10">
                <path d="M 2 9 A 8 8 0 0 1 10 1" fill="none" stroke="var(--ink-soft)" strokeWidth="1" strokeDasharray="1.5 1.2" />
                <line x1="2" y1="9" x2="2" y2="1" stroke="var(--ink-soft)" strokeWidth="1" />
              </svg>
              Door
            </div>
            <div className="legend-item">
              <svg className="legend-line" viewBox="0 0 24 10">
                <line x1="1" y1="5" x2="23" y2="5" stroke="var(--accent)" strokeWidth="1.5" />
                <line x1="6" y1="1" x2="6" y2="9" stroke="var(--accent)" strokeWidth="1.5" />
                <line x1="18" y1="1" x2="18" y2="9" stroke="var(--accent)" strokeWidth="1.5" />
              </svg>
              Window
            </div>
            <div className="legend-item">
              <svg className="legend-line" viewBox="0 0 24 10">
                <rect x="1" y="1" width="22" height="8" fill="none" stroke="var(--wood-dark)" strokeWidth="1" />
                <line x1="3" y1="9" x2="9" y2="1" stroke="var(--wood-dark)" strokeWidth="1" />
                <line x1="9" y1="9" x2="15" y2="1" stroke="var(--wood-dark)" strokeWidth="1" />
                <line x1="15" y1="9" x2="21" y2="1" stroke="var(--wood-dark)" strokeWidth="1" />
              </svg>
              Ramp
            </div>
            <div className="legend-item">
              <svg className="legend-line" viewBox="0 0 24 10">
                <line x1="1" y1="5" x2="23" y2="5" stroke="var(--warm)" strokeWidth="3" />
                <circle cx="1" cy="5" r="2" fill="var(--wall)" />
                <circle cx="23" cy="5" r="2" fill="var(--wall)" />
              </svg>
              Main gate
            </div>
          </div>
        </div>

        <div className="schedule-panel card">
          <h2>Room schedule</h2>
          <table className="schedule">
            <thead>
              <tr>
                <th>Room</th>
                <th>Zone</th>
                <th className="num">W &times; L (ft)</th>
                <th className="num">Area</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.id}
                  className={`sched-row ${activeRoomId === r.id ? "is-active" : ""}`}
                  onClick={() => setActiveRoomId((prev) => (prev === r.id ? null : r.id))}
                >
                  <td>{r.label}</td>
                  <td className="zone">{r.zone}</td>
                  <td className="num">
                    {fmt(r.width)} &times; {fmt(r.length)}
                  </td>
                  <td className="num">{fmt0(r.area)}</td>
                  <td>
                    {r.below_min_size ? <span className="chip warn">Under min</span> : <span className="chip ok">OK</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="schedule-total">
            <span>{rows.length} rooms</span>
            <span>{fmt0(totalArea)} sq ft</span>
          </div>
        </div>
      </div>
    </div>
  );
}
