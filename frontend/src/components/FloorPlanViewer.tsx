import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { CompoundWallStyle, FloorData, FurnitureItem, GateStyle, PlanData, RoomData } from "../api/types";
import { furnitureIconMarkup } from "./furnitureIcons";
import { bikeIconMarkup, carIconMarkup, shrubIconMarkup, treeIconMarkup } from "./siteIcons";
import FloorPlan3DView from "./FloorPlan3DView";
import "./floor-plan-viewer.css";

const FURNITURE_CATALOG: { type: string; label: string; w: number; l: number }[] = [
  { type: "sofa_set", label: "Sofa", w: 6, l: 2.5 },
  { type: "center_table", label: "Center table", w: 3, l: 1.5 },
  { type: "tv_unit", label: "TV unit", w: 4, l: 1.2 },
  { type: "dining_table_6", label: "Dining table (6)", w: 5, l: 5 },
  { type: "bed_king", label: "Bed (king)", w: 6.5, l: 6.5 },
  { type: "bed_queen", label: "Bed (queen)", w: 5, l: 6.5 },
  { type: "bed_single", label: "Bed (single)", w: 3.5, l: 6.5 },
  { type: "wardrobe", label: "Wardrobe", w: 4, l: 2 },
  { type: "dresser", label: "Dresser", w: 3, l: 1.5 },
  { type: "study_table", label: "Study table", w: 3.5, l: 2 },
  { type: "chair", label: "Chair", w: 1.5, l: 1.5 },
  { type: "bookshelf", label: "Bookshelf", w: 3, l: 1 },
  { type: "l_shape_counter", label: "Kitchen counter", w: 6, l: 2 },
  { type: "sink", label: "Sink", w: 2, l: 1.8 },
  { type: "stove", label: "Stove", w: 2.5, l: 2 },
  { type: "refrigerator", label: "Refrigerator", w: 2.5, l: 2.5 },
  { type: "washing_machine", label: "Washing machine", w: 2, l: 2 },
  { type: "mandir_unit", label: "Mandir unit", w: 2.5, l: 1.5 },
  { type: "wc", label: "WC", w: 2, l: 2.5 },
  { type: "wash_basin", label: "Wash basin", w: 2, l: 1.5 },
  { type: "shower", label: "Shower", w: 3, l: 3 },
  { type: "planters", label: "Planters", w: 2, l: 2 },
];

/** Curated furniture suggestions per room type -- shown first (and by
 * default selected) in the "Add" picker so a living room offers sofa/TV/
 * teapoy/planters instead of the full 21-item catalog. Any type not listed
 * here still falls back to the full catalog. */
const ROOM_FURNITURE_CATALOG: Record<string, string[]> = {
  living_room: ["sofa_set", "center_table", "tv_unit", "chair", "planters"],
  dining_room: ["dining_table_6", "chair", "planters"],
  kitchen: ["l_shape_counter", "sink", "stove", "refrigerator", "washing_machine"],
  master_bedroom: ["bed_king", "wardrobe", "dresser", "tv_unit", "chair"],
  bedroom: ["bed_queen", "bed_single", "wardrobe", "dresser", "study_table"],
  guest_room: ["bed_queen", "wardrobe", "dresser"],
  bathroom: ["wc", "wash_basin", "shower"],
  accessible_bathroom: ["wc", "wash_basin", "shower"],
  utility: ["washing_machine", "sink"],
  pooja_room: ["mandir_unit"],
  study_room: ["study_table", "chair", "bookshelf"],
  home_office: ["study_table", "chair", "bookshelf"],
  library: ["bookshelf", "study_table", "chair"],
  foyer: ["planters", "chair"],
  veranda: ["planters", "chair"],
  servant_room: ["bed_single", "wardrobe"],
  store_room: ["wardrobe", "bookshelf"],
};

/** Full catalog, partitioned into named categories for the "More furniture"
 * browser -- every item belongs to exactly one category here regardless of
 * which rooms suggest it in ROOM_FURNITURE_CATALOG above. */
const CATALOG_CATEGORIES: { label: string; types: string[] }[] = [
  { label: "Living & Dining", types: ["sofa_set", "center_table", "tv_unit", "dining_table_6"] },
  { label: "Bedroom", types: ["bed_king", "bed_queen", "bed_single", "wardrobe", "dresser"] },
  { label: "Study & Storage", types: ["study_table", "chair", "bookshelf"] },
  { label: "Kitchen", types: ["l_shape_counter", "sink", "stove", "refrigerator", "washing_machine"] },
  { label: "Bathroom", types: ["wc", "wash_basin", "shower"] },
  { label: "Pooja & Outdoor", types: ["mandir_unit", "planters"] },
];

function furnitureLabel(type: string): string {
  return FURNITURE_CATALOG.find((f) => f.type === type)?.label ?? type.replace(/_/g, " ");
}

/** Mirrors the backend's `ATTACHED_BATHROOM_INELIGIBLE_TYPES` so the "Add
 * attached bathroom" button doesn't even appear for a room the server would
 * always reject anyway. */
const ATTACHED_BATHROOM_INELIGIBLE_TYPES = new Set([
  "bathroom", "accessible_bathroom", "staircase", "veranda", "foyer",
  "balcony", "utility", "pooja_room", "kitchen",
]);

/** Mirrors the backend's `ROOM_REPLACE_INELIGIBLE_TYPES` -- staircase,
 * veranda and foyer are placed automatically by the generator (fixed strip,
 * pinned to the street-facing edge) and can't be swapped in or out here. */
const ROOM_REPLACE_INELIGIBLE_TYPES = new Set(["staircase", "veranda", "foyer"]);

/** Mirrors the backend's `ROOM_LIBRARY` labels for every type a room can be
 * replaced with (i.e. every type minus the ones above). */
const REPLACEABLE_ROOM_TYPES: { value: string; label: string }[] = [
  { value: "living_room", label: "Living Room" },
  { value: "master_bedroom", label: "Master Bedroom" },
  { value: "bedroom", label: "Bedroom" },
  { value: "kitchen", label: "Kitchen" },
  { value: "dining_room", label: "Dining Room" },
  { value: "pooja_room", label: "Pooja Room" },
  { value: "study_room", label: "Study Room" },
  { value: "bathroom", label: "Bathroom" },
  { value: "accessible_bathroom", label: "Accessible Bathroom" },
  { value: "utility", label: "Utility Room" },
  { value: "balcony", label: "Balcony" },
  { value: "home_office", label: "Home Office" },
  { value: "servant_room", label: "Servant Room" },
  { value: "store_room", label: "Store Room" },
  { value: "guest_room", label: "Guest Room" },
  { value: "gym", label: "Gym" },
  { value: "library", label: "Library" },
];

interface RoomRect {
  x: number;
  y: number;
  width: number;
  length: number;
}

type RoomResizeCorner = "resize-tl" | "resize-tr" | "resize-bl" | "resize-br";

interface RoomDragState {
  roomId: string;
  mode: "move" | RoomResizeCorner;
  startX: number;
  startY: number;
  orig: RoomRect;
  /** Snapshot of every other room's rect at drag start, used to stop a
   * resize from growing into a neighbor (which would leave the layout with
   * overlapping rooms and no valid shared wall for a doorway). */
  others: RoomRect[];
}

const NEIGHBOR_TOUCH_TOL = 0.05;

function overlaps1d(aMin: number, aMax: number, bMin: number, bMax: number): boolean {
  return aMin < bMax - 1e-6 && aMax > bMin + 1e-6;
}

/** Furthest a room's right edge may grow to (x + width) without crossing a
 * neighbor that currently sits at or beyond its right edge and overlaps it
 * vertically. Falls back to `bound` (the outline edge) if nothing is closer. */
function maxRightEdge(others: RoomRect[], room: RoomRect, bound: number): number {
  let limit = bound;
  for (const o of others) {
    if (!overlaps1d(o.y, o.y + o.length, room.y, room.y + room.length)) continue;
    if (o.x >= room.x + room.width - NEIGHBOR_TOUCH_TOL) limit = Math.min(limit, o.x);
  }
  return limit;
}

/** Furthest left a room's left edge may shrink to (x) without crossing a
 * neighbor to its left. Falls back to `bound` (the outline edge). */
function minLeftEdge(others: RoomRect[], room: RoomRect, bound: number): number {
  let limit = bound;
  for (const o of others) {
    if (!overlaps1d(o.y, o.y + o.length, room.y, room.y + room.length)) continue;
    if (o.x + o.width <= room.x + NEIGHBOR_TOUCH_TOL) limit = Math.max(limit, o.x + o.width);
  }
  return limit;
}

/** Furthest a room's bottom edge may grow to (y + length) without crossing a
 * neighbor below it. Falls back to `bound` (the outline edge). */
function maxBottomEdge(others: RoomRect[], room: RoomRect, bound: number): number {
  let limit = bound;
  for (const o of others) {
    if (!overlaps1d(o.x, o.x + o.width, room.x, room.x + room.width)) continue;
    if (o.y >= room.y + room.length - NEIGHBOR_TOUCH_TOL) limit = Math.min(limit, o.y);
  }
  return limit;
}

/** Furthest up a room's top edge may shrink to (y) without crossing a
 * neighbor above it. Falls back to `bound` (the outline edge). */
function minTopEdge(others: RoomRect[], room: RoomRect, bound: number): number {
  let limit = bound;
  for (const o of others) {
    if (!overlaps1d(o.x, o.x + o.width, room.x, room.x + room.width)) continue;
    if (o.y + o.length <= room.y + NEIGHBOR_TOUCH_TOL) limit = Math.max(limit, o.y + o.length);
  }
  return limit;
}

interface FurnitureResizeState {
  roomId: string;
  idx: number;
  orig: FurnitureItem;
}

const MIN_FURNITURE_SIZE = 0.5;

interface SharedWallHandle {
  /** `group1` is always on the west (axis "x") or north (axis "y") side. */
  group1: string[];
  group2: string[];
  axis: "x" | "y";
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

interface WallDragState {
  axis: "x" | "y";
  group1: string[];
  group2: string[];
  start: number;
  orig: Record<string, RoomRect>;
}

interface ParkingDragState {
  mode: "move" | "resize";
  startX: number;
  startY: number;
  orig: RoomRect;
}

const WALL_MATCH_TOL = 0.05;
const MIN_PARKING_SIZE = 3;

const round2 = (n: number) => Math.round(n * 100) / 100;

/** Transform for one furniture icon: the icon is authored in a 0..1 unit
 * square at its "natural" (unrotated) orientation, so a 90/270 rotation
 * must draw it at its pre-swap size and then rotate + recenter it into the
 * item's current (already width/length-swapped) bounding box -- naively
 * rotating an already-swapped scale(w,l) box spins it off-center. */
function furnitureTransform(item: FurnitureItem): string {
  const rotation = ((item.rotation % 360) + 360) % 360;
  const swapped = rotation % 180 !== 0;
  const naturalW = swapped ? item.l : item.w;
  const naturalL = swapped ? item.w : item.l;
  return (
    `translate(${item.x + item.w / 2} ${item.y + item.l / 2}) ` +
    `rotate(${rotation}) ` +
    `translate(${-naturalW / 2} ${-naturalL / 2}) ` +
    `scale(${naturalW} ${naturalL})`
  );
}

const CATEGORY: Record<string, "social" | "sleep" | "wet"> = {
  living_room: "social",
  dining_room: "social",
  veranda: "social",
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
function buildFloorSvg(
  floor: FloorData,
  plotLength: number,
  plotWidth: number,
  wallStyle: CompoundWallStyle,
  gateStyle: GateStyle,
  excludeFurnitureRoomId: string | null = null,
  showFurniture: boolean = true,
  furnitureOverride?: Record<string, FurnitureItem[]>
): { svg: string; viewBox: string } {
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
    const boundaryStroke =
      wallStyle === "fence" ? `stroke="var(--line-soft)" stroke-width="${unit * 0.06}" stroke-dasharray="${unit * 0.3} ${unit * 0.25}"` : "";
    svg += `<rect x="${plot.x}" y="${plot.y}" width="${plot.w}" height="${plot.l}" fill="var(--garden)" ${boundaryStroke} />`;

    // "wall" style: a solid compound wall traced around the plot perimeter,
    // with a gap left open at the main-gate span (drawn separately below).
    if (wallStyle === "wall") {
      const g = floor.main_gate;
      const corners: Record<string, [{ x: number; y: number }, { x: number; y: number }]> = {
        north: [{ x: plot.x, y: plot.y }, { x: plot.x + plot.w, y: plot.y }],
        south: [{ x: plot.x, y: plot.y + plot.l }, { x: plot.x + plot.w, y: plot.y + plot.l }],
        west: [{ x: plot.x, y: plot.y }, { x: plot.x, y: plot.y + plot.l }],
        east: [{ x: plot.x + plot.w, y: plot.y }, { x: plot.x + plot.w, y: plot.y + plot.l }],
      };
      let wallLines = `<g stroke="var(--wall)" stroke-width="${unit * 0.5}" stroke-linecap="square">`;
      for (const side of Object.keys(corners)) {
        const [a, b] = corners[side];
        if (g && g.side === side) {
          const horiz = side === "north" || side === "south";
          const gp1 = { x: g.x, y: g.y };
          const gp2 = horiz ? { x: g.x + g.width, y: g.y } : { x: g.x, y: g.y + g.width };
          const [gateStart, gateEnd] = (horiz ? gp1.x <= gp2.x : gp1.y <= gp2.y) ? [gp1, gp2] : [gp2, gp1];
          wallLines += `<line x1="${a.x}" y1="${a.y}" x2="${gateStart.x}" y2="${gateStart.y}" />`;
          wallLines += `<line x1="${gateEnd.x}" y1="${gateEnd.y}" x2="${b.x}" y2="${b.y}" />`;
        } else {
          wallLines += `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" />`;
        }
      }
      wallLines += `</g>`;
      svg += wallLines;
    }

    // subtle grass-blade texture across the whole yard
    svg += `<defs><pattern id="grassTexture" width="${unit * 1.2}" height="${unit * 1.2}" patternUnits="userSpaceOnUse">
      <line x1="0" y1="${unit * 1.2}" x2="${unit * 0.3}" y2="${unit * 0.6}" stroke="var(--garden-canopy)" stroke-width="${unit * 0.06}" opacity="0.35" />
      <line x1="${unit * 0.6}" y1="${unit * 1.2}" x2="${unit * 0.9}" y2="${unit * 0.6}" stroke="var(--garden-canopy)" stroke-width="${unit * 0.06}" opacity="0.35" />
    </pattern></defs>`;
    svg += `<rect x="${plot.x}" y="${plot.y}" width="${plot.w}" height="${plot.l}" fill="url(#grassTexture)" />`;

    // a paved walkway from the main gate to the entrance door, if both exist
    const entranceDoor = floor.doors.find((d) => d.type === "main_entrance");
    if (floor.main_gate && entranceDoor) {
      const g = floor.main_gate;
      const gx = g.side === "north" || g.side === "south" ? g.x + g.width / 2 : g.x;
      const gy = g.side === "east" || g.side === "west" ? g.y + g.width / 2 : g.y;
      const pathW = unit * 2.2;
      svg += `<line x1="${gx}" y1="${gy}" x2="${entranceDoor.center_x}" y2="${entranceDoor.center_y}" stroke="var(--stone)" stroke-width="${pathW}" stroke-linecap="round" />`;
      svg += `<line x1="${gx}" y1="${gy}" x2="${entranceDoor.center_x}" y2="${entranceDoor.center_y}" stroke="var(--stone-dark)" stroke-width="${unit * 0.1}" stroke-dasharray="${unit * 0.5} ${unit * 0.9}" />`;
    }

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
          const isShrub = seed % 3 === 0;
          const iconSize = isShrub ? treeSize * 0.65 : treeSize;
          const icon = isShrub ? shrubIconMarkup(seed) : treeIconMarkup(seed);
          svg += `<g transform="translate(${tx - iconSize / 2} ${ty - iconSize / 2}) scale(${iconSize} ${iconSize})" stroke-width="${unit * 0.06}">${icon}</g>`;
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
      // Icons are drawn front-to-back along their own local Y axis, side-to-side
      // along local X (see carIconMarkup/bikeIconMarkup). A parking slot is a
      // slotSize x cross rectangle, not a square, so scale each axis
      // independently instead of forcing a Math.min(...) square -- that was
      // shrinking every vehicle down to whichever dimension was smaller,
      // leaving it stranded in the middle of its slot looking half-sized.
      // When slots stack vertically (horiz false) the vehicle's natural
      // front-to-back axis needs to run along the real X axis instead, so the
      // whole icon is rotated 90 degrees in place around its own center.
      const placeIcon = (markup: string, marginFrac: number) => {
        const center = idx * slotSize + slotSize / 2;
        const w = slotSize * (1 - marginFrac * 2);
        const h = cross * (1 - marginFrac * 2);
        const cx = horiz ? p.x + center : p.x + cross / 2;
        const cy = horiz ? p.y + cross / 2 : p.y + center;
        const rotate = horiz ? "" : `rotate(90 ${cx} ${cy}) `;
        svg += `<g transform="${rotate}translate(${cx - w / 2} ${cy - h / 2}) scale(${w} ${h})" stroke-width="${unit * 0.06}">${markup}</g>`;
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

    if (gateStyle === "sliding") {
      // full-width overhead track, with a solid panel parked at one end (open position)
      const panelFrac = 0.55;
      const px2 = x1 + (x2 - x1) * panelFrac;
      const py2 = y1 + (y2 - y1) * panelFrac;
      svg += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="var(--wall)" stroke-width="${unit * 0.12}" stroke-dasharray="${unit * 0.5} ${unit * 0.3}" />`;
      svg += `<line x1="${x1}" y1="${y1}" x2="${px2}" y2="${py2}" stroke="var(--warm)" stroke-width="${unit * 0.4}" stroke-linecap="square" />`;
    } else {
      // swing: two leaves, each hinged at a gate post, opened inward toward the plot
      const midx = (x1 + x2) / 2, midy = (y1 + y2) / 2;
      const leafLen = g.width / 2;
      const nx = horiz ? 0 : g.side === "west" ? 1 : -1;
      const ny = horiz ? (g.side === "north" ? 1 : -1) : 0;
      for (const [hx, hy] of [[x1, y1], [x2, y2]] as const) {
        const tipX = hx + nx * leafLen, tipY = hy + ny * leafLen;
        const a1 = angleOf(hx, hy, tipX, tipY);
        const a2 = angleOf(hx, hy, midx, midy);
        const sweep = normalizeDelta(a2 - a1) > 0 ? 1 : 0;
        svg += `<g stroke="var(--warm)" stroke-width="${unit * 0.3}" fill="none">
          <line x1="${hx}" y1="${hy}" x2="${tipX}" y2="${tipY}" />
          <path d="M ${tipX} ${tipY} A ${leafLen} ${leafLen} 0 0 ${sweep} ${midx} ${midy}" stroke-dasharray="${unit * 0.35} ${unit * 0.28}" />
        </g>`;
      }
    }
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
    if (showFurniture && r.id !== excludeFurnitureRoomId) {
      const furnitureList = furnitureOverride && r.id in furnitureOverride ? furnitureOverride[r.id] : r.furniture ?? [];
      for (const it of furnitureList) {
        svg += `<g transform="${furnitureTransform(it)}" stroke-width="${unit * 0.05}">${furnitureIconMarkup(it.type)}</g>`;
      }
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

function sanitizeFileName(label: string): string {
  return label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "floor-plan";
}

interface PdfPageImage {
  jpegBytes: Uint8Array;
  imgWidthPx: number;
  imgHeightPx: number;
  pageWidthPt: number;
  pageHeightPt: number;
}

/** Wraps one JPEG image per page in a minimal, dependency-free multi-page PDF
 * (each page paints a single Image XObject to fill itself). Avoids pulling in
 * a PDF library for what is otherwise a handful of full-page images -- one
 * per floor. Byte offsets in the xref table must exactly match object start
 * positions, hence the manual bookkeeping. Object numbering: 1 = Catalog,
 * 2 = Pages tree, then 3 objects per page (Page, Image XObject, Contents). */
function buildMinimalPdf(pages: PdfPageImage[]): Uint8Array {
  const enc = new TextEncoder();
  const chunks: Uint8Array[] = [];
  const offsets: number[] = [0];
  let pos = 0;

  function push(bytes: Uint8Array) {
    chunks.push(bytes);
    pos += bytes.length;
  }
  function pushText(s: string) {
    push(enc.encode(s));
  }

  pushText("%PDF-1.4\n");

  const totalObjects = 2 + pages.length * 3;

  offsets[1] = pos;
  pushText("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n");

  const kids = pages.map((_, i) => `${3 + i * 3} 0 R`).join(" ");
  offsets[2] = pos;
  pushText(`2 0 obj\n<< /Type /Pages /Kids [${kids}] /Count ${pages.length} >>\nendobj\n`);

  pages.forEach((page, i) => {
    const pageObjNum = 3 + i * 3;
    const imgObjNum = pageObjNum + 1;
    const contentObjNum = pageObjNum + 2;

    offsets[pageObjNum] = pos;
    pushText(
      `${pageObjNum} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${page.pageWidthPt} ${page.pageHeightPt}] /Resources << /XObject << /Im0 ${imgObjNum} 0 R >> >> /Contents ${contentObjNum} 0 R >>\nendobj\n`
    );

    offsets[imgObjNum] = pos;
    pushText(
      `${imgObjNum} 0 obj\n<< /Type /XObject /Subtype /Image /Width ${page.imgWidthPx} /Height ${page.imgHeightPx} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${page.jpegBytes.length} >>\nstream\n`
    );
    push(page.jpegBytes);
    pushText("\nendstream\nendobj\n");

    const content = `q ${page.pageWidthPt} 0 0 ${page.pageHeightPt} 0 0 cm /Im0 Do Q`;
    const contentBytes = enc.encode(content);
    offsets[contentObjNum] = pos;
    pushText(`${contentObjNum} 0 obj\n<< /Length ${contentBytes.length} >>\nstream\n`);
    push(contentBytes);
    pushText("\nendstream\nendobj\n");
  });

  const xrefOffset = pos;
  let xref = `xref\n0 ${totalObjects + 1}\n0000000000 65535 f \n`;
  for (let i = 1; i <= totalObjects; i++) {
    xref += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`;
  }
  pushText(xref);
  pushText(`trailer\n<< /Size ${totalObjects + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`);

  const total = new Uint8Array(pos);
  let o = 0;
  for (const c of chunks) {
    total.set(c, o);
    o += c.length;
  }
  return total;
}

function dataUrlToBytes(dataUrl: string): Uint8Array {
  const base64 = dataUrl.slice(dataUrl.indexOf(",") + 1);
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

export default function FloorPlanViewer({
  plan,
  projectId,
  floorPlanId,
  onFurnitureSaved,
  onUndo,
  onRedo,
  canUndo = false,
  canRedo = false,
  undoRedoBusy = false,
  undoRedoError = null,
}: {
  plan: PlanData;
  projectId?: number;
  floorPlanId?: number;
  onFurnitureSaved?: (planData: PlanData) => void;
  onUndo?: () => void;
  onRedo?: () => void;
  canUndo?: boolean;
  canRedo?: boolean;
  undoRedoBusy?: boolean;
  undoRedoError?: string | null;
}) {
  const [activeFloorIdx, setActiveFloorIdx] = useState(0);
  const [activeRoomId, setActiveRoomId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"2d" | "3d">("2d");
  const [show2DFurniture, setShow2DFurniture] = useState(true);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; room: RoomData } | null>(null);
  const [downloading, setDownloading] = useState<null | "png" | "pdf">(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const editable = projectId != null && floorPlanId != null;
  const [editingFloorIdx, setEditingFloorIdx] = useState<number | null>(null);
  const [editingRoomId, setEditingRoomId] = useState<string | null>(null);
  const [localFurniture, setLocalFurniture] = useState<Record<string, FurnitureItem[]>>({});
  const [draggingIdx, setDraggingIdx] = useState<number | null>(null);
  const [furnitureResize, setFurnitureResize] = useState<FurnitureResizeState | null>(null);
  const [savingFurniture, setSavingFurniture] = useState(false);
  const [furnitureError, setFurnitureError] = useState<string | null>(null);
  const dragOffsetRef = useRef<{ dx: number; dy: number }>({ dx: 0, dy: 0 });
  const draggedItemRef = useRef<FurnitureItem | null>(null);

  const [editingRoomsFloorIdx, setEditingRoomsFloorIdx] = useState<number | null>(null);
  const [localRooms, setLocalRooms] = useState<Record<string, RoomRect>>({});
  const [roomDrag, setRoomDrag] = useState<RoomDragState | null>(null);
  const [wallDrag, setWallDrag] = useState<WallDragState | null>(null);
  const [localParking, setLocalParking] = useState<RoomRect | null>(null);
  const [parkingDrag, setParkingDrag] = useState<ParkingDragState | null>(null);
  const [savingRooms, setSavingRooms] = useState(false);
  const [roomEditError, setRoomEditError] = useState<string | null>(null);

  const [attachedBathroomBusy, setAttachedBathroomBusy] = useState<string | null>(null);
  const [attachedBathroomError, setAttachedBathroomError] = useState<string | null>(null);
  const [attachedBathroomNotice, setAttachedBathroomNotice] = useState<string | null>(null);

  const [replacingRoomId, setReplacingRoomId] = useState<string | null>(null);
  const [replaceSelection, setReplaceSelection] = useState<string>("");
  const [replaceBusy, setReplaceBusy] = useState<string | null>(null);
  const [replaceError, setReplaceError] = useState<string | null>(null);
  const [replaceNotice, setReplaceNotice] = useState<string | null>(null);

  const floor = plan.floors[activeFloorIdx];
  const isEditingThisFloor = editingFloorIdx === activeFloorIdx;
  const wallStyle = plan.meta.compound_wall_style ?? "wall";
  const gateStyle = plan.meta.gate_style ?? "swing";
  const { svg, viewBox } = useMemo(
    () =>
      buildFloorSvg(
        floor,
        plan.meta.plot_length,
        plan.meta.plot_width,
        wallStyle,
        gateStyle,
        isEditingThisFloor ? editingRoomId : null,
        show2DFurniture,
        isEditingThisFloor ? localFurniture : undefined
      ),
    [
      floor,
      plan.meta.plot_length,
      plan.meta.plot_width,
      wallStyle,
      gateStyle,
      isEditingThisFloor,
      editingRoomId,
      show2DFurniture,
      localFurniture,
    ]
  );
  const rows = useMemo(() => [...floor.rooms].sort((a, b) => b.area - a.area), [floor]);
  const totalArea = useMemo(() => rows.reduce((s, r) => s + r.area, 0), [rows]);

  const editingRoomType = editingRoomId ? floor.rooms.find((r) => r.id === editingRoomId)?.type : undefined;
  const curatedFurnitureTypes = editingRoomType ? ROOM_FURNITURE_CATALOG[editingRoomType] : undefined;
  const suggestedFurniture = curatedFurnitureTypes
    ? FURNITURE_CATALOG.filter((f) => curatedFurnitureTypes.includes(f.type))
    : [];
  const otherCategories = CATALOG_CATEGORIES.map((cat) => ({
    label: cat.label,
    items: FURNITURE_CATALOG.filter((f) => cat.types.includes(f.type) && !curatedFurnitureTypes?.includes(f.type)),
  })).filter((cat) => cat.items.length > 0);

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
    if (isEditingThisFloor) {
      if (roomId) setEditingRoomId(roomId);
      return;
    }
    setActiveRoomId((prev) => (prev === roomId ? null : roomId));
  }

  function startEditFurniture() {
    const init: Record<string, FurnitureItem[]> = {};
    for (const r of floor.rooms) init[r.id] = (r.furniture ?? []).map((f) => ({ ...f }));
    setLocalFurniture(init);
    setEditingFloorIdx(activeFloorIdx);
    setEditingRoomId(null);
    setFurnitureError(null);
  }

  function cancelEditFurniture() {
    setEditingFloorIdx(null);
    setEditingRoomId(null);
    setLocalFurniture({});
    setFurnitureError(null);
  }

  function screenToSvgPoint(clientX: number, clientY: number): { x: number; y: number } {
    const svgEl = svgRef.current;
    if (!svgEl) return { x: 0, y: 0 };
    const pt = svgEl.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const ctm = svgEl.getScreenCTM();
    if (!ctm) return { x: 0, y: 0 };
    const p = pt.matrixTransform(ctm.inverse());
    return { x: p.x, y: p.y };
  }

  function startDrag(e: React.MouseEvent, roomId: string, idx: number) {
    e.stopPropagation();
    e.preventDefault();
    const item = localFurniture[roomId]?.[idx];
    if (!item) return;
    const p = screenToSvgPoint(e.clientX, e.clientY);
    dragOffsetRef.current = { dx: p.x - item.x, dy: p.y - item.y };
    draggedItemRef.current = { ...item };
    setDraggingIdx(idx);
  }

  // While dragging, the item is free to move over any room (clamped to
  // whichever room is currently under the cursor, not just its own) but
  // stays in its origin room's array so the sidebar list doesn't jump mid-drag;
  // on drop, if it ended up centered over a different room, it's reassigned
  // there -- this is how a piece of furniture moves between rooms.
  useEffect(() => {
    if (draggingIdx === null || !editingRoomId) return;
    const originRoomId = editingRoomId;
    const originRoom = floor.rooms.find((r) => r.id === originRoomId);
    if (!originRoom) return;

    function roomAt(x: number, y: number) {
      return floor.rooms.find((r) => x >= r.x && x <= r.x + r.width && y >= r.y && y <= r.y + r.length) ?? null;
    }

    function handleMove(e: MouseEvent) {
      const p = screenToSvgPoint(e.clientX, e.clientY);
      const dragged = draggedItemRef.current;
      if (!dragged) return;
      const bounds = roomAt(p.x, p.y) ?? originRoom!;
      const maxX = Math.max(bounds.x + bounds.width - dragged.w, bounds.x);
      const maxY = Math.max(bounds.y + bounds.length - dragged.l, bounds.y);
      const nx = round2(Math.min(Math.max(p.x - dragOffsetRef.current.dx, bounds.x), maxX));
      const ny = round2(Math.min(Math.max(p.y - dragOffsetRef.current.dy, bounds.y), maxY));
      draggedItemRef.current = { ...dragged, x: nx, y: ny };
      setLocalFurniture((prev) => {
        const items = [...(prev[originRoomId] ?? [])];
        if (!items[draggingIdx!]) return prev;
        items[draggingIdx!] = { ...items[draggingIdx!], x: nx, y: ny };
        return { ...prev, [originRoomId]: items };
      });
    }

    function handleUp() {
      const dragged = draggedItemRef.current;
      if (dragged) {
        const cx = dragged.x + dragged.w / 2;
        const cy = dragged.y + dragged.l / 2;
        const destRoom = floor.rooms.find(
          (r) => r.id !== originRoomId && cx >= r.x && cx <= r.x + r.width && cy >= r.y && cy <= r.y + r.length
        );
        if (destRoom) {
          setLocalFurniture((prev) => {
            const originItems = [...(prev[originRoomId] ?? [])];
            const [moved] = originItems.splice(draggingIdx!, 1);
            if (!moved) return prev;
            const maxX = Math.max(destRoom.x + destRoom.width - moved.w, destRoom.x);
            const maxY = Math.max(destRoom.y + destRoom.length - moved.l, destRoom.y);
            const placed = {
              ...moved,
              x: round2(Math.min(Math.max(moved.x, destRoom.x), maxX)),
              y: round2(Math.min(Math.max(moved.y, destRoom.y), maxY)),
            };
            return {
              ...prev,
              [originRoomId]: originItems,
              [destRoom.id]: [...(prev[destRoom.id] ?? []), placed],
            };
          });
          setEditingRoomId(destRoom.id);
        }
      }
      draggedItemRef.current = null;
      setDraggingIdx(null);
    }
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
    return () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draggingIdx, editingRoomId, floor]);

  function startFurnitureResize(e: React.MouseEvent, roomId: string, idx: number) {
    e.stopPropagation();
    e.preventDefault();
    const item = localFurniture[roomId]?.[idx];
    if (!item) return;
    setFurnitureResize({ roomId, idx, orig: { ...item } });
  }

  // Resize handle sits at the item's (unrotated) bottom-right corner, same
  // convention as room resizing -- it grows/shrinks toward that corner and
  // is clamped so the item can never exceed its room's bounds.
  useEffect(() => {
    if (!furnitureResize) return;
    const { roomId, idx, orig } = furnitureResize;
    const room = floor.rooms.find((r) => r.id === roomId);
    if (!room) return;

    function handleMove(e: MouseEvent) {
      const p = screenToSvgPoint(e.clientX, e.clientY);
      const maxW = room!.x + room!.width - orig.x;
      const maxL = room!.y + room!.length - orig.y;
      const w = round2(Math.min(Math.max(p.x - orig.x, MIN_FURNITURE_SIZE), Math.max(maxW, MIN_FURNITURE_SIZE)));
      const l = round2(Math.min(Math.max(p.y - orig.y, MIN_FURNITURE_SIZE), Math.max(maxL, MIN_FURNITURE_SIZE)));
      setLocalFurniture((prev) => {
        const items = [...(prev[roomId] ?? [])];
        if (!items[idx]) return prev;
        items[idx] = { ...items[idx], w, l };
        return { ...prev, [roomId]: items };
      });
    }
    function handleUp() {
      setFurnitureResize(null);
    }
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
    return () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [furnitureResize, floor]);

  function addFurniture(roomId: string, catalogType: string) {
    const room = floor.rooms.find((r) => r.id === roomId);
    const spec = FURNITURE_CATALOG.find((f) => f.type === catalogType);
    if (!room || !spec) return;
    const w = Math.min(spec.w, room.width);
    const l = Math.min(spec.l, room.length);
    const x = room.x + (room.width - w) / 2;
    const y = room.y + (room.length - l) / 2;
    setLocalFurniture((prev) => ({
      ...prev,
      [roomId]: [...(prev[roomId] ?? []), { type: catalogType, x: round2(x), y: round2(y), w, l, rotation: 0 }],
    }));
  }

  function removeFurniture(roomId: string, idx: number) {
    setLocalFurniture((prev) => ({
      ...prev,
      [roomId]: (prev[roomId] ?? []).filter((_, i) => i !== idx),
    }));
  }

  function rotateFurniture(roomId: string, idx: number) {
    const room = floor.rooms.find((r) => r.id === roomId);
    if (!room) return;
    setLocalFurniture((prev) => {
      const items = prev[roomId] ?? [];
      const item = items[idx];
      if (!item) return prev;
      const nw = item.l;
      const nl = item.w;
      const maxX = Math.max(room.x + room.width - nw, room.x);
      const maxY = Math.max(room.y + room.length - nl, room.y);
      const nx = Math.min(item.x, maxX);
      const ny = Math.min(item.y, maxY);
      const updated = [...items];
      updated[idx] = { ...item, w: nw, l: nl, x: round2(nx), y: round2(ny), rotation: (item.rotation + 90) % 360 };
      return { ...prev, [roomId]: updated };
    });
  }

  async function saveFurniture() {
    if (!editable || editingFloorIdx === null || savingFurniture) return;
    setSavingFurniture(true);
    setFurnitureError(null);
    try {
      const updated = await api.updateFurniture(projectId!, floorPlanId!, {
        floor_number: floor.floor_number,
        furniture_by_room: localFurniture,
      });
      onFurnitureSaved?.(updated.plan_data);
      setEditingFloorIdx(null);
      setEditingRoomId(null);
    } catch (err) {
      setFurnitureError(err instanceof ApiError ? err.message : "Could not save furniture layout");
    } finally {
      setSavingFurniture(false);
    }
  }

  async function toggleAttachedBathroom(room: RoomData) {
    if (!editable || attachedBathroomBusy) return;
    setAttachedBathroomBusy(room.id);
    setAttachedBathroomError(null);
    setAttachedBathroomNotice(null);
    try {
      const result = room.attached_bathroom_id
        ? await api.removeAttachedBathroom(projectId!, floorPlanId!, room.id, floor.floor_number)
        : await api.addAttachedBathroom(projectId!, floorPlanId!, room.id, floor.floor_number);
      onFurnitureSaved?.(result.floor_plan.plan_data);
      if (result.warnings.length > 0) setAttachedBathroomNotice(result.warnings.join(" "));
    } catch (err) {
      setAttachedBathroomError(err instanceof ApiError ? err.message : "Could not update attached bathroom");
    } finally {
      setAttachedBathroomBusy(null);
    }
  }

  function startReplaceRoom(room: RoomData) {
    setReplacingRoomId(room.id);
    setReplaceSelection("");
    setReplaceError(null);
    setReplaceNotice(null);
  }

  function cancelReplaceRoom() {
    setReplacingRoomId(null);
    setReplaceSelection("");
    setReplaceError(null);
  }

  async function confirmReplaceRoom(room: RoomData) {
    if (!editable || replaceBusy || !replaceSelection) return;
    setReplaceBusy(room.id);
    setReplaceError(null);
    setReplaceNotice(null);
    try {
      const result = await api.replaceRoom(projectId!, floorPlanId!, room.id, {
        floor_number: floor.floor_number,
        new_type: replaceSelection,
      });
      onFurnitureSaved?.(result.floor_plan.plan_data);
      if (result.warnings.length > 0) setReplaceNotice(result.warnings.join(" "));
      setReplacingRoomId(null);
      setReplaceSelection("");
    } catch (err) {
      setReplaceError(err instanceof ApiError ? err.message : "Could not replace this room");
    } finally {
      setReplaceBusy(null);
    }
  }

  const isEditingRoomsThisFloor = editingRoomsFloorIdx === activeFloorIdx;
  const MIN_ROOM_SIZE = 3;

  // Ctrl/Cmd+Z to undo, Ctrl/Cmd+Shift+Z (or Ctrl+Y) to redo -- disabled
  // while typing in a form field, and while a local edit (furniture/room
  // drag) hasn't been saved or cancelled yet, same guard as the buttons.
  useEffect(() => {
    if (!editable || !onUndo) return;
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const typing = target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
      if (typing || isEditingThisFloor || isEditingRoomsThisFloor) return;
      const mod = e.ctrlKey || e.metaKey;
      const key = e.key.toLowerCase();
      const isUndoKey = mod && key === "z" && !e.shiftKey;
      const isRedoKey = (mod && key === "z" && e.shiftKey) || (e.ctrlKey && key === "y");
      if (!isUndoKey && !isRedoKey) return;
      e.preventDefault();
      if (isRedoKey) {
        if (canRedo && !undoRedoBusy) onRedo?.();
      } else if (canUndo && !undoRedoBusy) {
        onUndo?.();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [editable, onUndo, onRedo, canUndo, canRedo, undoRedoBusy, isEditingThisFloor, isEditingRoomsThisFloor]);

  function startEditRooms() {
    const init: Record<string, RoomRect> = {};
    for (const r of floor.rooms) {
      if (r.type !== "staircase") init[r.id] = { x: r.x, y: r.y, width: r.width, length: r.length };
    }
    setLocalRooms(init);
    setLocalParking(
      floor.parking
        ? { x: floor.parking.x, y: floor.parking.y, width: floor.parking.width, length: floor.parking.length }
        : null
    );
    setEditingRoomsFloorIdx(activeFloorIdx);
    setRoomEditError(null);
  }

  function cancelEditRooms() {
    setEditingRoomsFloorIdx(null);
    setLocalRooms({});
    setLocalParking(null);
    setRoomDrag(null);
    setParkingDrag(null);
    setRoomEditError(null);
  }

  function startRoomDrag(e: React.MouseEvent, roomId: string, mode: "move" | RoomResizeCorner) {
    e.stopPropagation();
    e.preventDefault();
    const rect = localRooms[roomId];
    if (!rect) return;
    const p = screenToSvgPoint(e.clientX, e.clientY);
    const others = Object.entries(localRooms)
      .filter(([id]) => id !== roomId)
      .map(([, r]) => r);
    setRoomDrag({ roomId, mode, startX: p.x, startY: p.y, orig: rect, others });
  }

  useEffect(() => {
    if (!roomDrag) return;
    const outline = floor.outline;

    function handleMove(e: MouseEvent) {
      const drag = roomDrag!;
      const p = screenToSvgPoint(e.clientX, e.clientY);
      const dx = p.x - drag.startX;
      const dy = p.y - drag.startY;
      const orig = drag.orig;

      let next: RoomRect;
      if (drag.mode === "move") {
        const maxX = outline.x + outline.width - orig.width;
        const maxY = outline.y + outline.length - orig.length;
        // Same neighbor clamp as resize -- otherwise a straight move can slide
        // the room's rect on top of another one instead of stopping at it.
        const minXBound = Math.max(outline.x, minLeftEdge(drag.others, orig, outline.x));
        const maxXBound = Math.min(maxX, maxRightEdge(drag.others, orig, outline.x + outline.width) - orig.width);
        const minYBound = Math.max(outline.y, minTopEdge(drag.others, orig, outline.y));
        const maxYBound = Math.min(maxY, maxBottomEdge(drag.others, orig, outline.y + outline.length) - orig.length);
        next = {
          x: Math.min(Math.max(orig.x + dx, minXBound), Math.max(maxXBound, minXBound)),
          y: Math.min(Math.max(orig.y + dy, minYBound), Math.max(maxYBound, minYBound)),
          width: orig.width,
          length: orig.length,
        };
      } else {
        // Each corner drags its own two edges while the opposite corner stays
        // anchored -- e.g. the top-left handle moves x/y and shrinks/grows
        // width/length toward the fixed bottom-right corner.
        const isLeft = drag.mode === "resize-tl" || drag.mode === "resize-bl";
        const isTop = drag.mode === "resize-tl" || drag.mode === "resize-tr";

        // A corner drag changes both axes at once, so the vertical clamp
        // needs to know where the horizontal edges are about to land (and
        // vice versa) -- otherwise a neighbor that only starts overlapping
        // because of the OTHER axis's growth slips through unclamped. Work
        // out each axis's naive post-drag span first (bounded only by the
        // outline and min size, not by neighbors) purely to feed the OTHER
        // axis's neighbor check below.
        const tentativeX = isLeft
          ? Math.min(Math.max(orig.x + dx, outline.x), orig.x + orig.width - MIN_ROOM_SIZE)
          : orig.x;
        const tentativeWidth = isLeft
          ? orig.x + orig.width - tentativeX
          : Math.min(Math.max(orig.width + dx, MIN_ROOM_SIZE), outline.x + outline.width - orig.x);
        const tentativeY = isTop
          ? Math.min(Math.max(orig.y + dy, outline.y), orig.y + orig.length - MIN_ROOM_SIZE)
          : orig.y;
        const tentativeLength = isTop
          ? orig.y + orig.length - tentativeY
          : Math.min(Math.max(orig.length + dy, MIN_ROOM_SIZE), outline.y + outline.length - orig.y);
        // The neighbor helpers use room.x/width to decide WHICH neighbors
        // count as "to my side" (a stable reference point) and room.y/length
        // only to test perpendicular overlap, or vice versa. Feeding them
        // the tentative value on BOTH axes is wrong: once the naive tentative
        // width already reaches past a neighbor, that neighbor's left edge
        // looks "behind" the (already-inflated) right edge and gets excluded
        // from the check entirely, silently removing the very clamp meant to
        // stop it. So keep the driven axis's own position/size at its
        // pre-drag (orig) value -- only the CROSS axis, which the neighbor
        // check uses purely for overlap detection, should use the fresh
        // tentative span.
        const forHorizontal: RoomRect = { x: orig.x, y: tentativeY, width: orig.width, length: tentativeLength };
        const forVertical: RoomRect = { x: tentativeX, y: orig.y, width: tentativeWidth, length: orig.length };

        let x = orig.x;
        let width: number;
        if (isLeft) {
          const rightEdge = orig.x + orig.width;
          const minX = Math.max(outline.x, minLeftEdge(drag.others, forHorizontal, outline.x));
          x = Math.min(Math.max(orig.x + dx, minX), rightEdge - MIN_ROOM_SIZE);
          width = rightEdge - x;
        } else {
          const maxRight = Math.min(outline.x + outline.width, maxRightEdge(drag.others, forHorizontal, outline.x + outline.width));
          width = Math.min(Math.max(orig.width + dx, MIN_ROOM_SIZE), maxRight - orig.x);
        }

        let y = orig.y;
        let length: number;
        if (isTop) {
          const bottomEdge = orig.y + orig.length;
          const minY = Math.max(outline.y, minTopEdge(drag.others, forVertical, outline.y));
          y = Math.min(Math.max(orig.y + dy, minY), bottomEdge - MIN_ROOM_SIZE);
          length = bottomEdge - y;
        } else {
          const maxBottom = Math.min(outline.y + outline.length, maxBottomEdge(drag.others, forVertical, outline.y + outline.length));
          length = Math.min(Math.max(orig.length + dy, MIN_ROOM_SIZE), maxBottom - orig.y);
        }

        next = { x, y, width, length };
      }

      setLocalRooms((prev) => ({
        ...prev,
        [drag.roomId]: { x: round2(next.x), y: round2(next.y), width: round2(next.width), length: round2(next.length) },
      }));
    }
    function handleUp() {
      setRoomDrag(null);
    }
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
    return () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomDrag, floor]);

  // A "clean cut" boundary: every room touching one side, stacked along the
  // perpendicular axis, exactly tiles the same span as every room touching
  // the other side, with no gaps -- e.g. a bedroom on one side facing both a
  // dining room and a bathroom stacked on the other. Dragging it resizes
  // every room on both sides at once (grow one side, shrink the other by the
  // same amount) so they always stay touching with no gap or overlap,
  // instead of the overlap error you'd get resizing just one room into its
  // neighbor.
  function tilesCleanly(ranges: [number, number][]): [number, number] | null {
    if (ranges.length === 0) return null;
    const sorted = [...ranges].sort((a, b) => a[0] - b[0]);
    for (let i = 1; i < sorted.length; i++) {
      if (Math.abs(sorted[i][0] - sorted[i - 1][1]) > WALL_MATCH_TOL) return null;
    }
    return [sorted[0][0], sorted[sorted.length - 1][1]];
  }

  const sharedWalls = useMemo<SharedWallHandle[]>(() => {
    if (!isEditingRoomsThisFloor) return [];
    const ids = Object.keys(localRooms);
    const walls: SharedWallHandle[] = [];
    const seen = new Set<string>();

    function addWall(axis: "x" | "y", coord: number, group1: string[], group2: string[]) {
      if (group1.length === 0 || group2.length === 0) return;
      const span1 = tilesCleanly(
        group1.map((id): [number, number] =>
          axis === "x"
            ? [localRooms[id].y, localRooms[id].y + localRooms[id].length]
            : [localRooms[id].x, localRooms[id].x + localRooms[id].width]
        )
      );
      const span2 = tilesCleanly(
        group2.map((id): [number, number] =>
          axis === "x"
            ? [localRooms[id].y, localRooms[id].y + localRooms[id].length]
            : [localRooms[id].x, localRooms[id].x + localRooms[id].width]
        )
      );
      if (!span1 || !span2) return;
      if (Math.abs(span1[0] - span2[0]) > WALL_MATCH_TOL || Math.abs(span1[1] - span2[1]) > WALL_MATCH_TOL) return;
      const key = `${axis}:${coord.toFixed(2)}:${[...group1].sort().join(",")}|${[...group2].sort().join(",")}`;
      if (seen.has(key)) return;
      seen.add(key);
      walls.push(
        axis === "x"
          ? { axis, group1, group2, x1: coord, y1: span1[0], x2: coord, y2: span1[1] }
          : { axis, group1, group2, x1: span1[0], y1: coord, x2: span1[1], y2: coord }
      );
    }

    const xCuts = new Set<number>();
    const yCuts = new Set<number>();
    for (const id of ids) {
      const r = localRooms[id];
      xCuts.add(round2(r.x));
      xCuts.add(round2(r.x + r.width));
      yCuts.add(round2(r.y));
      yCuts.add(round2(r.y + r.length));
    }
    for (const x of xCuts) {
      const west = ids.filter((id) => Math.abs(localRooms[id].x + localRooms[id].width - x) < WALL_MATCH_TOL);
      const east = ids.filter((id) => Math.abs(localRooms[id].x - x) < WALL_MATCH_TOL);
      addWall("x", x, west, east);
    }
    for (const y of yCuts) {
      const north = ids.filter((id) => Math.abs(localRooms[id].y + localRooms[id].length - y) < WALL_MATCH_TOL);
      const south = ids.filter((id) => Math.abs(localRooms[id].y - y) < WALL_MATCH_TOL);
      addWall("y", y, north, south);
    }
    return walls;
  }, [isEditingRoomsThisFloor, localRooms]);

  function startWallDrag(e: React.MouseEvent, wall: SharedWallHandle) {
    e.stopPropagation();
    e.preventDefault();
    const orig: Record<string, RoomRect> = {};
    for (const id of [...wall.group1, ...wall.group2]) {
      const r = localRooms[id];
      if (!r) return;
      orig[id] = r;
    }
    const p = screenToSvgPoint(e.clientX, e.clientY);
    setWallDrag({ axis: wall.axis, group1: wall.group1, group2: wall.group2, start: wall.axis === "x" ? p.x : p.y, orig });
  }

  useEffect(() => {
    if (!wallDrag) return;

    function handleMove(e: MouseEvent) {
      const drag = wallDrag!;
      const p = screenToSvgPoint(e.clientX, e.clientY);
      const current = drag.axis === "x" ? p.x : p.y;

      let minDelta = -Infinity;
      let maxDelta = Infinity;
      for (const id of drag.group1) {
        const size = drag.axis === "x" ? drag.orig[id].width : drag.orig[id].length;
        minDelta = Math.max(minDelta, MIN_ROOM_SIZE - size);
      }
      for (const id of drag.group2) {
        const size = drag.axis === "x" ? drag.orig[id].width : drag.orig[id].length;
        maxDelta = Math.min(maxDelta, size - MIN_ROOM_SIZE);
      }
      const delta = Math.min(Math.max(current - drag.start, minDelta), maxDelta);

      setLocalRooms((prev) => {
        const next = { ...prev };
        for (const id of drag.group1) {
          const orig = drag.orig[id];
          next[id] =
            drag.axis === "x" ? { ...orig, width: round2(orig.width + delta) } : { ...orig, length: round2(orig.length + delta) };
        }
        for (const id of drag.group2) {
          const orig = drag.orig[id];
          next[id] =
            drag.axis === "x"
              ? { ...orig, x: round2(orig.x + delta), width: round2(orig.width - delta) }
              : { ...orig, y: round2(orig.y + delta), length: round2(orig.length - delta) };
        }
        return next;
      });
    }
    function handleUp() {
      setWallDrag(null);
    }
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
    return () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wallDrag]);

  function startParkingDrag(e: React.MouseEvent, mode: "move" | "resize") {
    e.stopPropagation();
    e.preventDefault();
    if (!localParking) return;
    const p = screenToSvgPoint(e.clientX, e.clientY);
    setParkingDrag({ mode, startX: p.x, startY: p.y, orig: localParking });
  }

  useEffect(() => {
    if (!parkingDrag) return;
    // Parking is allowed to sit within the mandatory front setback, so it's
    // clamped to the whole plot, not the (already setback-shrunk) outline
    // rooms are clamped to.
    const plotW = plan.meta.plot_width;
    const plotL = plan.meta.plot_length;

    function handleMove(e: MouseEvent) {
      const drag = parkingDrag!;
      const p = screenToSvgPoint(e.clientX, e.clientY);
      const dx = p.x - drag.startX;
      const dy = p.y - drag.startY;
      const orig = drag.orig;

      let next: RoomRect;
      if (drag.mode === "move") {
        const maxX = plotW - orig.width;
        const maxY = plotL - orig.length;
        next = {
          x: Math.min(Math.max(orig.x + dx, 0), Math.max(maxX, 0)),
          y: Math.min(Math.max(orig.y + dy, 0), Math.max(maxY, 0)),
          width: orig.width,
          length: orig.length,
        };
      } else {
        const maxWidth = plotW - orig.x;
        const maxLength = plotL - orig.y;
        next = {
          x: orig.x,
          y: orig.y,
          width: Math.min(Math.max(orig.width + dx, MIN_PARKING_SIZE), maxWidth),
          length: Math.min(Math.max(orig.length + dy, MIN_PARKING_SIZE), maxLength),
        };
      }
      setLocalParking({ x: round2(next.x), y: round2(next.y), width: round2(next.width), length: round2(next.length) });
    }
    function handleUp() {
      setParkingDrag(null);
    }
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
    return () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parkingDrag, plan.meta.plot_width, plan.meta.plot_length]);

  async function saveRoomLayout() {
    if (!editable || editingRoomsFloorIdx === null || savingRooms) return;
    const changed: Record<string, RoomRect> = {};
    for (const r of floor.rooms) {
      const local = localRooms[r.id];
      if (!local) continue;
      if (local.x !== r.x || local.y !== r.y || local.width !== r.width || local.length !== r.length) {
        changed[r.id] = local;
      }
    }
    const parkingChanged =
      !!localParking &&
      !!floor.parking &&
      (localParking.x !== floor.parking.x ||
        localParking.y !== floor.parking.y ||
        localParking.width !== floor.parking.width ||
        localParking.length !== floor.parking.length);

    if (Object.keys(changed).length === 0 && !parkingChanged) {
      cancelEditRooms();
      return;
    }
    setSavingRooms(true);
    setRoomEditError(null);
    try {
      let latestPlanData = null;
      if (Object.keys(changed).length > 0) {
        const updated = await api.updateRoomLayout(projectId!, floorPlanId!, {
          floor_number: floor.floor_number,
          rooms: changed,
        });
        latestPlanData = updated.plan_data;
      }
      if (parkingChanged && localParking) {
        const updated = await api.updateParking(projectId!, floorPlanId!, {
          floor_number: floor.floor_number,
          parking: localParking,
        });
        latestPlanData = updated.plan_data;
      }
      if (latestPlanData) onFurnitureSaved?.(latestPlanData);
      setEditingRoomsFloorIdx(null);
      setLocalRooms({});
      setLocalParking(null);
    } catch (err) {
      setRoomEditError(err instanceof ApiError ? err.message : "Could not save room layout");
    } finally {
      setSavingRooms(false);
    }
  }

  /** Builds a standalone, self-styled SVG document string for any floor (not
   * just the currently displayed one) straight from buildFloorSvg's output,
   * so every floor can be rasterized for export without having to switch
   * React state and wait for a re-render per floor. Assembled via a detached
   * DOM node + XMLSerializer (the same route the live view's own markup goes
   * through via dangerouslySetInnerHTML) rather than raw string
   * concatenation, since buildFloorSvg's fragments are HTML-parser-lenient
   * markup, not necessarily strict XML -- feeding them to an <img> as
   * image/svg+xml requires well-formed XML, which only the DOM round-trip
   * guarantees. */
  function floorSvgMarkup(floorIdx: number): { markup: string; width: number; height: number } {
    const floorData = plan.floors[floorIdx];
    const { svg: innerSvg, viewBox: vb } = buildFloorSvg(
      floorData, plan.meta.plot_length, plan.meta.plot_width, wallStyle, gateStyle, null
    );

    const svgNs = "http://www.w3.org/2000/svg";
    const svgEl = document.createElementNS(svgNs, "svg");
    svgEl.setAttribute("xmlns", svgNs);
    svgEl.setAttribute("viewBox", vb);
    const g = document.createElementNS(svgNs, "g");
    g.innerHTML = innerSvg;
    svgEl.appendChild(g);

    const [, , vbWidth, vbHeight] = vb.split(/\s+/).map(Number);
    const targetWidth = 2200;
    const targetHeight = Math.round((vbHeight / vbWidth) * targetWidth);
    svgEl.setAttribute("width", String(targetWidth));
    svgEl.setAttribute("height", String(targetHeight));

    // The markup fills/strokes reference the page's CSS custom properties
    // (var(--room-social) etc.) -- once serialized and rendered as a
    // standalone image those variables have no :root to resolve against, so
    // inline their current computed values as an embedded stylesheet first.
    const varNames = Array.from(new Set(Array.from(innerSvg.matchAll(/var\((--[a-z0-9-]+)\)/gi)).map((m) => m[1])));
    const rootStyles = getComputedStyle(document.documentElement);
    const varDecls = varNames.map((name) => `${name}: ${rootStyles.getPropertyValue(name).trim()};`).join(" ");
    const styleEl = document.createElementNS(svgNs, "style");
    styleEl.textContent = `:root { ${varDecls} }`;
    svgEl.insertBefore(styleEl, svgEl.firstChild);

    const markup = new XMLSerializer().serializeToString(svgEl);
    return { markup, width: targetWidth, height: targetHeight };
  }

  function rasterizeSvgMarkup(markup: string, width: number, height: number): Promise<HTMLCanvasElement> {
    const svgUrl = URL.createObjectURL(new Blob([markup], { type: "image/svg+xml;charset=utf-8" }));
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        URL.revokeObjectURL(svgUrl);
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          reject(new Error("no canvas context"));
          return;
        }
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, width, height);
        ctx.drawImage(img, 0, 0, width, height);
        resolve(canvas);
      };
      img.onerror = () => {
        URL.revokeObjectURL(svgUrl);
        reject(new Error("svg failed to rasterize"));
      };
      img.src = svgUrl;
    });
  }

  function renderToCanvas(floorIdx: number = activeFloorIdx): Promise<HTMLCanvasElement> {
    const { markup, width, height } = floorSvgMarkup(floorIdx);
    return rasterizeSvgMarkup(markup, width, height);
  }

  async function handleDownloadPng() {
    if (downloading) return;
    setDownloading("png");
    try {
      const canvas = await renderToCanvas();
      const blob: Blob | null = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
      if (!blob) return;
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `${sanitizeFileName(floor.label)}-floor-plan.png`;
      link.click();
      URL.revokeObjectURL(link.href);
    } finally {
      setDownloading(null);
    }
  }

  async function handleDownloadPdf() {
    if (downloading) return;
    setDownloading("pdf");
    try {
      const pages: PdfPageImage[] = [];
      for (let i = 0; i < plan.floors.length; i++) {
        const canvas = await renderToCanvas(i);
        const jpegDataUrl = canvas.toDataURL("image/jpeg", 0.92);
        // 200 DPI: physical page size in points (1/72in) derived from pixel size.
        pages.push({
          jpegBytes: dataUrlToBytes(jpegDataUrl),
          imgWidthPx: canvas.width,
          imgHeightPx: canvas.height,
          pageWidthPt: (canvas.width * 72) / 200,
          pageHeightPt: (canvas.height * 72) / 200,
        });
      }
      const pdfBytes = buildMinimalPdf(pages);
      const blob = new Blob([Uint8Array.from(pdfBytes)], { type: "application/pdf" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download =
        plan.floors.length > 1 ? "floor-plan-all-floors.pdf" : `${sanitizeFileName(floor.label)}-floor-plan.pdf`;
      link.click();
      URL.revokeObjectURL(link.href);
    } finally {
      setDownloading(null);
    }
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
            <div className="drawing-panel-info">
              <span className="drawing-panel-plot">
                Plot: {fmt0(plan.meta.plot_width)}&#8242; &times; {fmt0(plan.meta.plot_length)}&#8242;
              </span>
              <span className="drawing-panel-floor">
                {plan.meta.facing.charAt(0).toUpperCase() + plan.meta.facing.slice(1)} facing
              </span>
            </div>
          </div>

          <div className="drawing-panel-toolbar">
            <div className="toolbar-row">
              <div className="view-mode-toggle" role="group" aria-label="View mode">
                <button
                  type="button"
                  className={`btn btn-secondary view-mode-btn ${viewMode === "2d" ? "is-active" : ""}`}
                  onClick={() => setViewMode("2d")}
                >
                  2D Plan
                </button>
                <button
                  type="button"
                  className={`btn btn-secondary view-mode-btn ${viewMode === "3d" ? "is-active" : ""}`}
                  onClick={() => setViewMode("3d")}
                >
                  3D View
                </button>
              </div>
              {editable && onUndo && (
                <div className="undo-redo-group" role="group" aria-label="Undo/redo">
                  <button
                    type="button"
                    className="btn btn-secondary undo-redo-btn"
                    disabled={!canUndo || undoRedoBusy || isEditingThisFloor || isEditingRoomsThisFloor}
                    title={
                      isEditingThisFloor || isEditingRoomsThisFloor
                        ? "Finish or cancel the current edit first"
                        : "Undo last change"
                    }
                    onClick={onUndo}
                  >
                    ↶ Undo
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary undo-redo-btn"
                    disabled={!canRedo || undoRedoBusy || isEditingThisFloor || isEditingRoomsThisFloor}
                    title={
                      isEditingThisFloor || isEditingRoomsThisFloor
                        ? "Finish or cancel the current edit first"
                        : "Redo last undone change"
                    }
                    onClick={onRedo}
                  >
                    ↷ Redo
                  </button>
                </div>
              )}
              {viewMode === "2d" && !isEditingThisFloor && (
                <label className="show-furniture-toggle">
                  <input
                    type="checkbox"
                    checked={show2DFurniture}
                    onChange={(e) => setShow2DFurniture(e.target.checked)}
                  />
                  Show furniture
                </label>
              )}
            </div>

            {viewMode === "2d" && (
              <div className="toolbar-row">
                <button type="button" className="btn btn-secondary drawing-panel-download" onClick={handleDownloadPng} disabled={!!downloading}>
                  {downloading === "png" ? "Preparing…" : "Download PNG"}
                </button>
                <button type="button" className="btn btn-secondary drawing-panel-download" onClick={handleDownloadPdf} disabled={!!downloading}>
                  {downloading === "pdf"
                    ? "Preparing…"
                    : plan.floors.length > 1
                      ? `Download PDF (${plan.floors.length} floors)`
                      : "Download PDF"}
                </button>
                {editable && !isEditingThisFloor && !isEditingRoomsThisFloor && (
                  <button type="button" className="btn btn-secondary drawing-panel-download" onClick={startEditFurniture}>
                    Edit furniture
                  </button>
                )}
                {editable && isEditingThisFloor && (
                  <>
                    <button type="button" className="btn btn-primary drawing-panel-download" onClick={saveFurniture} disabled={savingFurniture}>
                      {savingFurniture ? "Saving…" : "Save layout"}
                    </button>
                    <button type="button" className="btn btn-secondary drawing-panel-download" onClick={cancelEditFurniture} disabled={savingFurniture}>
                      Cancel
                    </button>
                  </>
                )}
                {editable && !isEditingRoomsThisFloor && !isEditingThisFloor && (
                  <button type="button" className="btn btn-secondary drawing-panel-download" onClick={startEditRooms}>
                    Edit rooms
                  </button>
                )}
                {editable && isEditingRoomsThisFloor && (
                  <>
                    <button type="button" className="btn btn-primary drawing-panel-download" onClick={saveRoomLayout} disabled={savingRooms}>
                      {savingRooms ? "Saving…" : "Save room layout"}
                    </button>
                    <button type="button" className="btn btn-secondary drawing-panel-download" onClick={cancelEditRooms} disabled={savingRooms}>
                      Cancel
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
          {editable && undoRedoError && <div className="error-banner">{undoRedoError}</div>}
          {viewMode === "3d" ? (
            <FloorPlan3DView plan={plan} />
          ) : (
          <div
            className="drawing-svg-wrap"
            onMouseMove={handleMouseMove}
            onMouseLeave={() => setTooltip(null)}
            onClick={handleClick}
          >
            <svg
              ref={svgRef}
              viewBox={viewBox}
              className={activeRoomId ? `has-active` : ""}
            >
              <g dangerouslySetInnerHTML={{ __html: svg }} />
              {isEditingThisFloor && editingRoomId && (
                <g>
                  {(localFurniture[editingRoomId] ?? []).map((item, idx) => (
                    <g
                      key={idx}
                      transform={furnitureTransform(item)}
                      className={`furniture-editable ${draggingIdx === idx ? "is-dragging" : ""}`}
                      onMouseDown={(e) => startDrag(e, editingRoomId, idx)}
                    >
                      <rect x="0" y="0" width="1" height="1" fill="transparent" />
                      <g dangerouslySetInnerHTML={{ __html: furnitureIconMarkup(item.type) }} />
                    </g>
                  ))}
                  {(localFurniture[editingRoomId] ?? []).map((item, idx) => {
                    const handleSize = Math.min(Math.max(Math.min(item.w, item.l) * 0.35, 0.4), 1.1);
                    return (
                      <rect
                        key={`resize-${idx}`}
                        x={item.x + item.w - handleSize}
                        y={item.y + item.l - handleSize}
                        width={handleSize}
                        height={handleSize}
                        className={`furniture-resize-handle ${furnitureResize?.idx === idx ? "is-dragging" : ""}`}
                        onMouseDown={(e) => startFurnitureResize(e, editingRoomId, idx)}
                      />
                    );
                  })}
                </g>
              )}
              {isEditingRoomsThisFloor && (
                <g>
                  {/* Three paint layers so overlapping hit-areas resolve
                      predictably: room bodies (move) at the bottom, wall-drag
                      lines in the middle (so they win over a room body along
                      a shared boundary), and corner resize handles last/on
                      top (so a resize handle always wins even where a wall
                      line's stroke happens to pass right by a corner). */}
                  {Object.entries(localRooms).map(([roomId, rect]) => (
                    <g key={`body-${roomId}`} className={roomDrag?.roomId === roomId ? "room-editable is-dragging" : "room-editable"}>
                      <rect
                        x={rect.x}
                        y={rect.y}
                        width={rect.width}
                        height={rect.length}
                        className="room-edit-rect"
                        onMouseDown={(e) => startRoomDrag(e, roomId, "move")}
                      />
                      <text x={rect.x + rect.width / 2} y={rect.y + rect.length / 2} className="room-edit-label">
                        {fmt(rect.width)}&#8242; &times; {fmt(rect.length)}&#8242;
                      </text>
                    </g>
                  ))}
                  {sharedWalls.map((wall) => {
                    const key = `${wall.axis}:${[...wall.group1].sort().join(",")}|${[...wall.group2].sort().join(",")}`;
                    const isDragging =
                      !!wallDrag &&
                      wallDrag.axis === wall.axis &&
                      [...wallDrag.group1].sort().join(",") === [...wall.group1].sort().join(",") &&
                      [...wallDrag.group2].sort().join(",") === [...wall.group2].sort().join(",");
                    return (
                      <line
                        key={key}
                        x1={wall.x1}
                        y1={wall.y1}
                        x2={wall.x2}
                        y2={wall.y2}
                        className={`wall-edit-handle wall-edit-handle-${wall.axis} ${isDragging ? "is-dragging" : ""}`}
                        onMouseDown={(e) => startWallDrag(e, wall)}
                      />
                    );
                  })}
                  {Object.entries(localRooms).map(([roomId, rect]) => {
                    const handleSize = Math.min(rect.width, rect.length) * 0.18 || 1;
                    const corners: { mode: RoomResizeCorner; x: number; y: number; cursor: string }[] = [
                      { mode: "resize-tl", x: rect.x, y: rect.y, cursor: "nwse" },
                      { mode: "resize-tr", x: rect.x + rect.width - handleSize, y: rect.y, cursor: "nesw" },
                      { mode: "resize-bl", x: rect.x, y: rect.y + rect.length - handleSize, cursor: "nesw" },
                      {
                        mode: "resize-br",
                        x: rect.x + rect.width - handleSize,
                        y: rect.y + rect.length - handleSize,
                        cursor: "nwse",
                      },
                    ];
                    return (
                      <g key={`handles-${roomId}`}>
                        {corners.map((c) => (
                          <rect
                            key={c.mode}
                            x={c.x}
                            y={c.y}
                            width={handleSize}
                            height={handleSize}
                            className={`room-edit-handle room-edit-handle-${c.cursor}`}
                            onMouseDown={(e) => startRoomDrag(e, roomId, c.mode)}
                          />
                        ))}
                      </g>
                    );
                  })}
                  {localParking && (() => {
                    const handleSize = Math.min(localParking.width, localParking.length) * 0.18 || 1;
                    return (
                      <g className={parkingDrag ? "parking-editable is-dragging" : "parking-editable"}>
                        <rect
                          x={localParking.x}
                          y={localParking.y}
                          width={localParking.width}
                          height={localParking.length}
                          className="parking-edit-rect"
                          onMouseDown={(e) => startParkingDrag(e, "move")}
                        />
                        <text
                          x={localParking.x + localParking.width / 2}
                          y={localParking.y + localParking.length / 2}
                          className="room-edit-label"
                        >
                          Parking {fmt(localParking.width)}&#8242; &times; {fmt(localParking.length)}&#8242;
                        </text>
                        <rect
                          x={localParking.x + localParking.width - handleSize}
                          y={localParking.y + localParking.length - handleSize}
                          width={handleSize}
                          height={handleSize}
                          className="room-edit-handle"
                          onMouseDown={(e) => startParkingDrag(e, "resize")}
                        />
                      </g>
                    );
                  })()}
                </g>
              )}
            </svg>
            <style>{`.room-outline[data-room="${isEditingThisFloor ? editingRoomId : activeRoomId}"] { stroke: var(--accent) !important; }`}</style>
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
          )}
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

        <div className="fpv-side">
        <div className="schedule-panel card">
          <h2>Room schedule</h2>
          {editable && attachedBathroomError && <div className="error-banner">{attachedBathroomError}</div>}
          {editable && attachedBathroomNotice && <div className="notice-banner">{attachedBathroomNotice}</div>}
          {editable && replaceError && <div className="error-banner">{replaceError}</div>}
          {editable && replaceNotice && <div className="notice-banner">{replaceNotice}</div>}
          <table className="schedule">
            <thead>
              <tr>
                <th>Room</th>
                <th>Zone</th>
                <th className="num">W &times; L (ft)</th>
                <th className="num">Area</th>
                <th></th>
                {editable && <th></th>}
                {editable && <th></th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <Fragment key={r.id}>
                <tr
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
                  {editable && (
                    <td className="attached-bath-cell" onClick={(e) => e.stopPropagation()}>
                      {r.attached_to ? (
                        <span className="muted">Attached</span>
                      ) : ATTACHED_BATHROOM_INELIGIBLE_TYPES.has(r.type) ? null : (
                        <button
                          type="button"
                          className={r.attached_bathroom_id ? "attached-bath-btn is-remove" : "attached-bath-btn"}
                          disabled={attachedBathroomBusy === r.id}
                          title={r.attached_bathroom_id ? `Remove attached bathroom from ${r.label}` : `Add attached bathroom to ${r.label}`}
                          onClick={() => toggleAttachedBathroom(r)}
                        >
                          {attachedBathroomBusy === r.id
                            ? "…"
                            : r.attached_bathroom_id
                              ? "Remove bath"
                              : "+ Bath"}
                        </button>
                      )}
                    </td>
                  )}
                  {editable && (
                    <td className="replace-room-cell" onClick={(e) => e.stopPropagation()}>
                      {ROOM_REPLACE_INELIGIBLE_TYPES.has(r.type) ? null : (
                        <button
                          type="button"
                          className="replace-room-btn"
                          disabled={replaceBusy === r.id}
                          title={`Replace ${r.label} with a different room type`}
                          onClick={() => (replacingRoomId === r.id ? cancelReplaceRoom() : startReplaceRoom(r))}
                        >
                          Replace
                        </button>
                      )}
                    </td>
                  )}
                </tr>
                {editable && replacingRoomId === r.id && (
                  <tr className="replace-room-row" onClick={(e) => e.stopPropagation()}>
                    <td colSpan={7}>
                      <div className="replace-room-picker">
                        <span>Replace {r.label} with:</span>
                        <select value={replaceSelection} onChange={(e) => setReplaceSelection(e.target.value)}>
                          <option value="">Choose a room type…</option>
                          {REPLACEABLE_ROOM_TYPES.filter((t) => t.value !== r.type).map((t) => (
                            <option key={t.value} value={t.value}>
                              {t.label}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          className="btn btn-primary"
                          disabled={!replaceSelection || replaceBusy === r.id}
                          onClick={() => confirmReplaceRoom(r)}
                        >
                          {replaceBusy === r.id ? "Replacing…" : "Apply"}
                        </button>
                        <button type="button" className="btn btn-secondary" onClick={cancelReplaceRoom}>
                          Cancel
                        </button>
                      </div>
                    </td>
                  </tr>
                )}
                </Fragment>
              ))}
            </tbody>
          </table>
          <div className="schedule-total">
            <span>{rows.length} rooms</span>
            <span>{fmt0(totalArea)} sq ft</span>
          </div>
        </div>

        {isEditingThisFloor && (
          <div className="furniture-editor card">
            <h2>Furniture</h2>
            {furnitureError && <div className="error-banner">{furnitureError}</div>}
            {!editingRoomId ? (
              <p className="muted">Click a room in the plan to edit its furniture.</p>
            ) : (
              <>
                <div className="furniture-editor-room">
                  {floor.rooms.find((r) => r.id === editingRoomId)?.label ?? editingRoomId}
                </div>
                <ul className="furniture-list">
                  {(localFurniture[editingRoomId] ?? []).map((item, idx) => (
                    <li key={idx} className={draggingIdx === idx ? "is-dragging" : ""}>
                      <span>{furnitureLabel(item.type)}</span>
                      <div className="furniture-item-actions">
                        <button type="button" title="Rotate 90°" onClick={() => rotateFurniture(editingRoomId, idx)}>
                          ⟳
                        </button>
                        <button type="button" title="Remove" onClick={() => removeFurniture(editingRoomId, idx)}>
                          ×
                        </button>
                      </div>
                    </li>
                  ))}
                  {(localFurniture[editingRoomId] ?? []).length === 0 && (
                    <li className="muted">No furniture in this room yet.</li>
                  )}
                </ul>
                <div className="furniture-catalog">
                  {suggestedFurniture.length > 0 && (
                    <div className="furniture-catalog-section">
                      <div className="furniture-catalog-heading">
                        Suggested for {floor.rooms.find((r) => r.id === editingRoomId)?.label ?? "this room"}
                      </div>
                      <div className="furniture-catalog-grid">
                        {suggestedFurniture.map((f) => (
                          <button
                            key={f.type}
                            type="button"
                            className="furniture-catalog-btn"
                            title={`Add ${f.label}`}
                            onClick={() => addFurniture(editingRoomId, f.type)}
                          >
                            <svg
                              viewBox="0 0 1 1"
                              className="furniture-catalog-icon"
                              dangerouslySetInnerHTML={{ __html: furnitureIconMarkup(f.type) }}
                            />
                            <span>{f.label}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  {otherCategories.length > 0 && (
                    <details className="furniture-catalog-more">
                      <summary>More furniture</summary>
                      {otherCategories.map((cat) => (
                        <div className="furniture-catalog-section" key={cat.label}>
                          <div className="furniture-catalog-heading">{cat.label}</div>
                          <div className="furniture-catalog-grid">
                            {cat.items.map((f) => (
                              <button
                                key={f.type}
                                type="button"
                                className="furniture-catalog-btn"
                                title={`Add ${f.label}`}
                                onClick={() => addFurniture(editingRoomId, f.type)}
                              >
                                <svg
                                  viewBox="0 0 1 1"
                                  className="furniture-catalog-icon"
                                  dangerouslySetInnerHTML={{ __html: furnitureIconMarkup(f.type) }}
                                />
                                <span>{f.label}</span>
                              </button>
                            ))}
                          </div>
                        </div>
                      ))}
                    </details>
                  )}
                </div>
                <p className="muted furniture-hint">
                  Drag items in the plan to reposition them, or drag one across a wall into another room to move it
                  there.
                </p>
              </>
            )}
          </div>
        )}
        {isEditingRoomsThisFloor && (
          <div className="furniture-editor card">
            <h2>Room layout</h2>
            {roomEditError && <div className="error-banner">{roomEditError}</div>}
            <p className="muted">
              Drag a room to move it, or drag any of its 4 corner handles to resize. Drag a highlighted wall shared by
              two rooms to resize both at once -- e.g. shrink a dining room and extend the bedroom next to it in one
              move. The staircase can't be moved (it has to stay aligned across floors), and moving or resizing a
              room clears its furniture.
            </p>
            <ul className="furniture-list">
              {floor.rooms
                .filter((r) => r.type !== "staircase")
                .map((r) => {
                  const local = localRooms[r.id];
                  if (!local) return null;
                  return (
                    <li key={r.id}>
                      <span>{r.label}</span>
                      <span>
                        {fmt(local.width)}&#8242; &times; {fmt(local.length)}&#8242;
                      </span>
                    </li>
                  );
                })}
            </ul>
          </div>
        )}
        </div>
      </div>
    </div>
  );
}
