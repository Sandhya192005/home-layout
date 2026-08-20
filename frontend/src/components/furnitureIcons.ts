/**
 * Top-down architectural furniture symbols, each drawn in a 0..1 x 0..1 unit
 * square (x = along width, y = along length). The caller wraps the returned
 * markup in <g transform="translate(x y) scale(w l)">, so every icon is
 * defined once and stretched to the item's real footprint. Strokes use
 * vector-effect="non-scaling-stroke" so line thickness stays constant
 * regardless of how much a given piece gets stretched.
 */

const S = `stroke="var(--ink-soft)" vector-effect="non-scaling-stroke"`;

function rect(x: number, y: number, w: number, h: number, fill: string, rx = 0) {
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="${fill}" ${S} />`;
}
function line(x1: number, y1: number, x2: number, y2: number) {
  return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" ${S} />`;
}
function circle(cx: number, cy: number, r: number, fill = "none") {
  return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${fill}" ${S} />`;
}
function ellipse(cx: number, cy: number, rx: number, ry: number, fill: string) {
  return `<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" fill="${fill}" ${S} />`;
}

const FABRIC = "var(--fabric)";
const WOOD = "var(--wood)";
const STONE = "var(--stone)";
const WATER = "var(--water)";
const SURFACE = "var(--surface)";

function sofa(): string {
  return (
    rect(0.03, 0.03, 0.94, 0.94, FABRIC, 0.1) +
    rect(0.03, 0.03, 0.94, 0.22, "var(--fabric-dark)", 0.06) + // backrest
    rect(0.03, 0.03, 0.15, 0.94, "var(--fabric-dark)", 0.06) + // left arm
    rect(0.82, 0.03, 0.15, 0.94, "var(--fabric-dark)", 0.06) + // right arm
    // seat cushion seams
    line(0.36, 0.25, 0.36, 0.94) +
    line(0.63, 0.25, 0.63, 0.94) +
    circle(0.195, 0.14, 0.05, "var(--fabric-dark)") + // scatter cushion accents
    circle(0.805, 0.14, 0.05, "var(--fabric-dark)")
  );
}
function chairIcon(): string {
  return (
    rect(0.1, 0.25, 0.8, 0.7, FABRIC, 0.1) +
    rect(0.15, 0.03, 0.7, 0.2, "var(--fabric-dark)", 0.05) +
    line(0.32, 0.05, 0.32, 0.21) +
    line(0.5, 0.05, 0.5, 0.21) +
    line(0.68, 0.05, 0.68, 0.21)
  );
}
function table(): string {
  return (
    rect(0.05, 0.05, 0.9, 0.9, WOOD, 0.05) +
    rect(0.14, 0.14, 0.72, 0.72, "var(--wood-dark)", 0.03) +
    line(0.14, 0.36, 0.86, 0.36) +
    line(0.14, 0.63, 0.86, 0.63)
  );
}
function tvUnit(): string {
  return (
    rect(0.02, 0.4, 0.96, 0.28, WOOD, 0.03) +
    rect(0.08, 0.44, 0.35, 0.06, "var(--wood-dark)") +
    rect(0.57, 0.44, 0.35, 0.06, "var(--wood-dark)") +
    rect(0.22, 0.03, 0.56, 0.3, "var(--ink)", 0.02) + // wall-mounted screen, drawn above the unit
    rect(0.26, 0.07, 0.48, 0.22, "var(--ink-faint)")
  );
}
function bed(pillows: number): string {
  let s = rect(0.03, 0.03, 0.94, 0.94, FABRIC, 0.06);
  s += rect(0.03, 0.0, 0.94, 0.08, WOOD, 0.02); // headboard
  const pw = pillows === 1 ? 0.5 : 0.38;
  if (pillows === 1) {
    s += rect((1 - pw) / 2, 0.12, pw, 0.2, SURFACE, 0.04);
  } else {
    s += rect(0.08, 0.12, pw, 0.2, SURFACE, 0.04) + rect(1 - 0.08 - pw, 0.12, pw, 0.2, SURFACE, 0.04);
  }
  s += `<rect x="0.06" y="0.4" width="0.88" height="0.54" rx="0.03" fill="var(--fabric-dark)" ${S} />`;
  s += line(0.08, 0.78, 0.92, 0.78); // foot fold
  return s;
}
function wardrobe(): string {
  return (
    rect(0.03, 0.03, 0.94, 0.94, WOOD) +
    line(0.5, 0.03, 0.5, 0.97) +
    line(0.15, 0.03, 0.3, 0.15) +
    line(0.85, 0.03, 0.7, 0.15) +
    circle(0.44, 0.5, 0.025, "var(--wood-dark)") + // door handles
    circle(0.56, 0.5, 0.025, "var(--wood-dark)")
  );
}
function dresser(): string {
  let s = rect(0.03, 0.03, 0.94, 0.94, WOOD);
  for (const y of [0.27, 0.5, 0.73]) {
    s += line(0.1, y, 0.9, y);
    s += circle(0.5, y - 0.06, 0.03, "var(--wood-dark)");
  }
  return s;
}
function counterL(): string {
  // L-shaped counter: full-width strip plus a returning leg
  return (
    `<path d="M 0.03 0.03 L 0.97 0.03 L 0.97 0.4 L 0.4 0.4 L 0.4 0.97 L 0.03 0.97 Z" fill="${STONE}" ${S} />` +
    line(0.03, 0.2, 0.97, 0.2)
  );
}
function sinkIcon(): string {
  return rect(0.05, 0.15, 0.9, 0.7, STONE, 0.05) + ellipse(0.5, 0.5, 0.32, 0.24, WATER) + circle(0.5, 0.5, 0.04, "var(--ink-faint)");
}
function stove(): string {
  let s = rect(0.03, 0.03, 0.94, 0.94, "var(--ink-faint)", 0.04);
  for (const cx of [0.28, 0.72]) {
    for (const cy of [0.3, 0.7]) {
      s += circle(cx, cy, 0.13, "var(--stone-dark)");
    }
  }
  return s;
}
function fridge(): string {
  return rect(0.05, 0.03, 0.9, 0.94, STONE, 0.04) + line(0.05, 0.42, 0.95, 0.42) + line(0.85, 0.5, 0.85, 0.62);
}
function diningTable(seats: number): string {
  let s = ellipse(0.5, 0.5, 0.38, 0.34, WOOD) + ellipse(0.5, 0.5, 0.28, 0.24, "var(--wood-dark)");
  const chairSize = 0.16;
  for (let i = 0; i < seats; i++) {
    const angle = (i / seats) * Math.PI * 2 - Math.PI / 2;
    const cx = 0.5 + (0.38 + chairSize * 0.75) * Math.cos(angle);
    const cy = 0.5 + (0.34 + chairSize * 0.75) * Math.sin(angle);
    const deg = (angle * 180) / Math.PI + 90;
    s += `<g transform="rotate(${deg.toFixed(1)} ${cx.toFixed(3)} ${cy.toFixed(3)})">` +
      rect(cx - chairSize / 2, cy - chairSize / 2, chairSize, chairSize, FABRIC, 0.03) +
      `</g>`;
  }
  return s;
}
function mandir(): string {
  return `<path d="M 0.5 0.02 L 0.92 0.32 L 0.92 0.97 L 0.08 0.97 L 0.08 0.32 Z" fill="${WOOD}" ${S} />` + line(0.08, 0.32, 0.92, 0.32);
}
function bookshelfIcon(): string {
  let s = rect(0.03, 0.03, 0.94, 0.94, WOOD);
  for (const x of [0.27, 0.5, 0.73]) s += line(x, 0.03, x, 0.97);
  return s;
}
function wc(): string {
  return rect(0.2, 0.02, 0.6, 0.28, STONE, 0.04) + ellipse(0.5, 0.66, 0.34, 0.3, SURFACE);
}
function washBasin(): string {
  return rect(0.05, 0.15, 0.9, 0.55, STONE, 0.06) + ellipse(0.5, 0.42, 0.3, 0.2, WATER);
}
function showerIcon(): string {
  return rect(0.03, 0.03, 0.94, 0.94, WATER) + line(0.15, 0.15, 0.85, 0.85) + line(0.85, 0.15, 0.15, 0.85) + circle(0.5, 0.5, 0.08, SURFACE);
}
function grabBar(): string {
  // wall-mounted accessibility grab bar: a bar with two mounting posts
  return line(0.05, 0.5, 0.95, 0.5) + circle(0.08, 0.5, 0.09, "var(--ink-faint)") + circle(0.92, 0.5, 0.09, "var(--ink-faint)");
}
function washingMachine(): string {
  return rect(0.05, 0.05, 0.9, 0.9, STONE, 0.06) + circle(0.5, 0.55, 0.28, "var(--water)");
}
function planters(): string {
  let s = "";
  for (const [cx, cy] of [
    [0.25, 0.3],
    [0.75, 0.3],
    [0.5, 0.7],
  ]) {
    s += circle(cx, cy, 0.18, "var(--garden-canopy)");
  }
  return s;
}
function equipmentRack(): string {
  let s = rect(0.03, 0.03, 0.94, 0.94, STONE);
  for (const x of [0.2, 0.4, 0.6, 0.8]) s += line(x, 0.03, x, 0.97);
  for (const y of [0.3, 0.6]) s += line(0.03, y, 0.97, y);
  return s;
}
function staircase(): string {
  let s = rect(0.03, 0.03, 0.94, 0.94, "var(--stone-dark)");
  for (let i = 1; i < 9; i++) {
    s += line(0.03, i / 9, 0.97, i / 9);
  }
  s += `<path d="M 0.03 0.03 L 0.97 0.97" stroke="var(--ink-faint)" stroke-dasharray="0.04 0.04" vector-effect="non-scaling-stroke" />`;
  return s;
}
function genericBox(): string {
  return rect(0.06, 0.06, 0.88, 0.88, SURFACE, 0.04) + line(0.06, 0.06, 0.94, 0.94) + line(0.94, 0.06, 0.06, 0.94);
}

const ICONS: Record<string, () => string> = {
  sofa_set: sofa,
  center_table: table,
  tv_unit: tvUnit,
  bed_king: () => bed(2),
  bed_queen: () => bed(2),
  bed_single: () => bed(1),
  wardrobe: wardrobe,
  dresser: dresser,
  l_shape_counter: counterL,
  sink: sinkIcon,
  wash_sink: sinkIcon,
  stove: stove,
  refrigerator: fridge,
  dining_table_6: () => diningTable(6),
  mandir_unit: mandir,
  study_table: table,
  desk: table,
  chair: chairIcon,
  bookshelf: bookshelfIcon,
  shelving: bookshelfIcon,
  wc: wc,
  wash_basin: washBasin,
  shower: showerIcon,
  grab_bar: grabBar,
  washing_machine: washingMachine,
  planters: planters,
  equipment_rack: equipmentRack,
  staircase: staircase,
};

export function furnitureIconMarkup(type: string): string {
  const fn = ICONS[type] ?? genericBox;
  return fn();
}
