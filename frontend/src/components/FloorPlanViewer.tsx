import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { CompoundWallStyle, FloorData, FurnitureItem, GateStyle, PlanData, RoomData } from "../api/types";
import { furnitureIconMarkup } from "./furnitureIcons";
import { bikeIconMarkup, carIconMarkup, shrubIconMarkup, treeIconMarkup } from "./siteIcons";
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

function furnitureLabel(type: string): string {
  return FURNITURE_CATALOG.find((f) => f.type === type)?.label ?? type.replace(/_/g, " ");
}

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
  excludeFurnitureRoomId: string | null = null
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
    if (r.id !== excludeFurnitureRoomId) {
      for (const it of r.furniture ?? []) {
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

/** Wraps a JPEG image in a minimal, dependency-free single-page PDF (one
 * Image XObject painted to fill the page). Avoids pulling in a PDF library
 * for what is otherwise a one-image document. Byte offsets in the xref table
 * must exactly match object start positions, hence the manual bookkeeping. */
function buildMinimalPdf(
  jpegBytes: Uint8Array,
  imgWidthPx: number,
  imgHeightPx: number,
  pageWidthPt: number,
  pageHeightPt: number
): Uint8Array {
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

  offsets[1] = pos;
  pushText("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n");

  offsets[2] = pos;
  pushText("2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n");

  offsets[3] = pos;
  pushText(
    `3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pageWidthPt} ${pageHeightPt}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>\nendobj\n`
  );

  offsets[4] = pos;
  pushText(
    `4 0 obj\n<< /Type /XObject /Subtype /Image /Width ${imgWidthPx} /Height ${imgHeightPx} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpegBytes.length} >>\nstream\n`
  );
  push(jpegBytes);
  pushText("\nendstream\nendobj\n");

  const content = `q ${pageWidthPt} 0 0 ${pageHeightPt} 0 0 cm /Im0 Do Q`;
  const contentBytes = enc.encode(content);
  offsets[5] = pos;
  pushText(`5 0 obj\n<< /Length ${contentBytes.length} >>\nstream\n`);
  push(contentBytes);
  pushText("\nendstream\nendobj\n");

  const xrefOffset = pos;
  let xref = `xref\n0 6\n0000000000 65535 f \n`;
  for (let i = 1; i <= 5; i++) {
    xref += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`;
  }
  pushText(xref);
  pushText(`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`);

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
}: {
  plan: PlanData;
  projectId?: number;
  floorPlanId?: number;
  onFurnitureSaved?: (planData: PlanData) => void;
}) {
  const [activeFloorIdx, setActiveFloorIdx] = useState(0);
  const [activeRoomId, setActiveRoomId] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; room: RoomData } | null>(null);
  const [downloading, setDownloading] = useState<null | "png" | "pdf">(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const editable = projectId != null && floorPlanId != null;
  const [editingFloorIdx, setEditingFloorIdx] = useState<number | null>(null);
  const [editingRoomId, setEditingRoomId] = useState<string | null>(null);
  const [localFurniture, setLocalFurniture] = useState<Record<string, FurnitureItem[]>>({});
  const [draggingIdx, setDraggingIdx] = useState<number | null>(null);
  const [addType, setAddType] = useState(FURNITURE_CATALOG[0].type);
  const [savingFurniture, setSavingFurniture] = useState(false);
  const [furnitureError, setFurnitureError] = useState<string | null>(null);
  const dragOffsetRef = useRef<{ dx: number; dy: number }>({ dx: 0, dy: 0 });

  const floor = plan.floors[activeFloorIdx];
  const isEditingThisFloor = editingFloorIdx === activeFloorIdx;
  const wallStyle = plan.meta.compound_wall_style ?? "wall";
  const gateStyle = plan.meta.gate_style ?? "swing";
  const { svg, viewBox } = useMemo(
    () => buildFloorSvg(floor, plan.meta.plot_length, plan.meta.plot_width, wallStyle, gateStyle, isEditingThisFloor ? editingRoomId : null),
    [floor, plan.meta.plot_length, plan.meta.plot_width, wallStyle, gateStyle, isEditingThisFloor, editingRoomId]
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
    setDraggingIdx(idx);
  }

  useEffect(() => {
    if (draggingIdx === null || !editingRoomId) return;
    const room = floor.rooms.find((r) => r.id === editingRoomId);
    if (!room) return;

    function handleMove(e: MouseEvent) {
      const p = screenToSvgPoint(e.clientX, e.clientY);
      setLocalFurniture((prev) => {
        const items = prev[editingRoomId!] ?? [];
        const item = items[draggingIdx!];
        if (!item || !room) return prev;
        const maxX = Math.max(room.x + room.width - item.w, room.x);
        const maxY = Math.max(room.y + room.length - item.l, room.y);
        const nx = Math.min(Math.max(p.x - dragOffsetRef.current.dx, room.x), maxX);
        const ny = Math.min(Math.max(p.y - dragOffsetRef.current.dy, room.y), maxY);
        const updated = [...items];
        updated[draggingIdx!] = { ...item, x: round2(nx), y: round2(ny) };
        return { ...prev, [editingRoomId!]: updated };
      });
    }
    function handleUp() {
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

  function renderToCanvas(): Promise<HTMLCanvasElement> {
    const svgEl = svgRef.current;
    if (!svgEl) return Promise.reject(new Error("no svg"));

    const clone = svgEl.cloneNode(true) as SVGSVGElement;
    clone.removeAttribute("class");
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");

    // The markup fills/strokes reference the page's CSS custom properties
    // (var(--room-social) etc.) -- once serialized and rendered as a
    // standalone image those variables have no :root to resolve against, so
    // inline their current computed values as an embedded stylesheet first.
    const varNames = Array.from(new Set(Array.from(clone.outerHTML.matchAll(/var\((--[a-z0-9-]+)\)/gi)).map((m) => m[1])));
    const rootStyles = getComputedStyle(document.documentElement);
    const varDecls = varNames.map((name) => `${name}: ${rootStyles.getPropertyValue(name).trim()};`).join(" ");
    const styleEl = document.createElementNS("http://www.w3.org/2000/svg", "style");
    styleEl.textContent = `:root { ${varDecls} }`;
    clone.insertBefore(styleEl, clone.firstChild);

    const vb = clone.viewBox.baseVal;
    const targetWidth = 2200;
    const targetHeight = Math.round((vb.height / vb.width) * targetWidth);
    clone.setAttribute("width", String(targetWidth));
    clone.setAttribute("height", String(targetHeight));

    const svgString = new XMLSerializer().serializeToString(clone);
    const svgUrl = URL.createObjectURL(new Blob([svgString], { type: "image/svg+xml;charset=utf-8" }));

    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        URL.revokeObjectURL(svgUrl);
        const canvas = document.createElement("canvas");
        canvas.width = targetWidth;
        canvas.height = targetHeight;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          reject(new Error("no canvas context"));
          return;
        }
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, targetWidth, targetHeight);
        ctx.drawImage(img, 0, 0, targetWidth, targetHeight);
        resolve(canvas);
      };
      img.onerror = () => {
        URL.revokeObjectURL(svgUrl);
        reject(new Error("svg failed to rasterize"));
      };
      img.src = svgUrl;
    });
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
      const canvas = await renderToCanvas();
      const jpegDataUrl = canvas.toDataURL("image/jpeg", 0.92);
      const jpegBytes = dataUrlToBytes(jpegDataUrl);
      // 200 DPI: physical page size in points (1/72in) derived from pixel size.
      const pageWidthPt = (canvas.width * 72) / 200;
      const pageHeightPt = (canvas.height * 72) / 200;
      const pdfBytes = buildMinimalPdf(jpegBytes, canvas.width, canvas.height, pageWidthPt, pageHeightPt);
      const blob = new Blob([Uint8Array.from(pdfBytes)], { type: "application/pdf" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `${sanitizeFileName(floor.label)}-floor-plan.pdf`;
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
            <div className="drawing-panel-meta">
              <span className="drawing-panel-plot">
                Plot: {fmt0(plan.meta.plot_width)}&#8242; &times; {fmt0(plan.meta.plot_length)}&#8242;
              </span>
              <span className="drawing-panel-floor">
                {plan.meta.facing.charAt(0).toUpperCase() + plan.meta.facing.slice(1)} facing
              </span>
              <button type="button" className="btn btn-secondary drawing-panel-download" onClick={handleDownloadPng} disabled={!!downloading}>
                {downloading === "png" ? "Preparing…" : "Download PNG"}
              </button>
              <button type="button" className="btn btn-secondary drawing-panel-download" onClick={handleDownloadPdf} disabled={!!downloading}>
                {downloading === "pdf" ? "Preparing…" : "Download PDF"}
              </button>
              {editable && !isEditingThisFloor && (
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
            </div>
          </div>
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
                <div className="furniture-add-row">
                  <select value={addType} onChange={(e) => setAddType(e.target.value)}>
                    {FURNITURE_CATALOG.map((f) => (
                      <option key={f.type} value={f.type}>
                        {f.label}
                      </option>
                    ))}
                  </select>
                  <button type="button" className="btn btn-secondary" onClick={() => addFurniture(editingRoomId, addType)}>
                    Add
                  </button>
                </div>
                <p className="muted furniture-hint">Drag items in the plan to reposition them.</p>
              </>
            )}
          </div>
        )}
        </div>
      </div>
    </div>
  );
}
