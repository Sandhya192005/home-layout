/**
 * Top-down architectural furniture symbols, each drawn in a 0..1 x 0..1 unit
 * square (x = along width, y = along length). The caller wraps the returned
 * markup in <g transform="translate(x y) scale(w l)">, so every icon is
 * defined once and stretched to the item's real footprint. Strokes use
 * vector-effect="non-scaling-stroke" so line thickness stays constant
 * regardless of how much a given piece gets stretched.
 */

const S = `stroke="var(--ink-soft)" vector-effect="non-scaling-stroke"`;
const FILL = `fill="var(--surface)"`;

function rect(x: number, y: number, w: number, h: number, rx = 0) {
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" ${FILL} ${S} />`;
}
function line(x1: number, y1: number, x2: number, y2: number) {
  return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" ${S} />`;
}
function circle(cx: number, cy: number, r: number, filled = false) {
  return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${filled ? "var(--ink-soft)" : "none"}" ${S} />`;
}
function ellipse(cx: number, cy: number, rx: number, ry: number) {
  return `<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" ${FILL} ${S} />`;
}

function sofa(): string {
  return (
    rect(0.03, 0.03, 0.94, 0.94, 0.06) +
    rect(0.03, 0.03, 0.94, 0.24) + // backrest
    rect(0.03, 0.03, 0.16, 0.94) + // left arm
    rect(0.81, 0.03, 0.16, 0.94) + // right arm
    line(0.36, 0.27, 0.36, 0.97) +
    line(0.63, 0.27, 0.63, 0.97)
  );
}
function chairIcon(): string {
  return rect(0.1, 0.25, 0.8, 0.7, 0.08) + rect(0.15, 0.03, 0.7, 0.2);
}
function table(): string {
  return rect(0.05, 0.05, 0.9, 0.9, 0.04) + rect(0.16, 0.16, 0.68, 0.68);
}
function tvUnit(): string {
  return rect(0.02, 0.35, 0.96, 0.3) + rect(0.3, 0.05, 0.16, 0.16) + rect(0.54, 0.05, 0.16, 0.16);
}
function bed(pillows: number): string {
  let s = rect(0.03, 0.03, 0.94, 0.94, 0.05);
  const pw = pillows === 1 ? 0.5 : 0.38;
  if (pillows === 1) {
    s += rect((1 - pw) / 2, 0.08, pw, 0.22, 0.04);
  } else {
    s += rect(0.08, 0.08, pw, 0.22, 0.04) + rect(1 - 0.08 - pw, 0.08, pw, 0.22, 0.04);
  }
  s += line(0.08, 0.38, 0.92, 0.38); // blanket fold
  s += line(0.08, 0.78, 0.92, 0.78); // foot fold
  return s;
}
function wardrobe(): string {
  return (
    rect(0.03, 0.03, 0.94, 0.94) +
    line(0.5, 0.03, 0.5, 0.97) +
    line(0.15, 0.03, 0.3, 0.15) +
    line(0.85, 0.03, 0.7, 0.15)
  );
}
function dresser(): string {
  let s = rect(0.03, 0.03, 0.94, 0.94);
  for (const y of [0.27, 0.5, 0.73]) {
    s += line(0.1, y, 0.9, y);
    s += circle(0.5, y - 0.06, 0.03, true);
  }
  return s;
}
function counterL(): string {
  // L-shaped counter: full-width strip plus a returning leg
  return (
    `<path d="M 0.03 0.03 L 0.97 0.03 L 0.97 0.4 L 0.4 0.4 L 0.4 0.97 L 0.03 0.97 Z" ${FILL} ${S} />` +
    line(0.03, 0.2, 0.97, 0.2)
  );
}
function sinkIcon(): string {
  return rect(0.05, 0.15, 0.9, 0.7, 0.05) + ellipse(0.5, 0.5, 0.32, 0.24) + circle(0.5, 0.5, 0.04, true);
}
function stove(): string {
  let s = rect(0.03, 0.03, 0.94, 0.94, 0.04);
  for (const cx of [0.28, 0.72]) {
    for (const cy of [0.3, 0.7]) {
      s += circle(cx, cy, 0.13);
    }
  }
  return s;
}
function fridge(): string {
  return rect(0.05, 0.03, 0.9, 0.94, 0.04) + line(0.05, 0.42, 0.95, 0.42) + line(0.85, 0.5, 0.85, 0.62);
}
function diningTable(seats: number): string {
  let s = ellipse(0.5, 0.5, 0.46, 0.44);
  const perSide = Math.max(1, Math.round(seats / 2));
  for (let i = 0; i < perSide; i++) {
    const cx = (i + 1) / (perSide + 1);
    s += rect(cx - 0.06, -0.12, 0.12, 0.12);
    s += rect(cx - 0.06, 1.0, 0.12, 0.12);
  }
  return s;
}
function mandir(): string {
  return `<path d="M 0.5 0.02 L 0.92 0.32 L 0.92 0.97 L 0.08 0.97 L 0.08 0.32 Z" ${FILL} ${S} />` + line(0.08, 0.32, 0.92, 0.32);
}
function bookshelfIcon(): string {
  let s = rect(0.03, 0.03, 0.94, 0.94);
  for (const x of [0.27, 0.5, 0.73]) s += line(x, 0.03, x, 0.97);
  return s;
}
function wc(): string {
  return rect(0.2, 0.02, 0.6, 0.28, 0.04) + ellipse(0.5, 0.66, 0.34, 0.3);
}
function washBasin(): string {
  return rect(0.05, 0.15, 0.9, 0.55, 0.06) + ellipse(0.5, 0.42, 0.3, 0.2);
}
function showerIcon(): string {
  return rect(0.03, 0.03, 0.94, 0.94) + line(0.15, 0.15, 0.85, 0.85) + line(0.85, 0.15, 0.15, 0.85) + circle(0.5, 0.5, 0.08);
}
function washingMachine(): string {
  return rect(0.05, 0.05, 0.9, 0.9, 0.06) + circle(0.5, 0.55, 0.28);
}
function planters(): string {
  let s = "";
  for (const [cx, cy] of [
    [0.25, 0.3],
    [0.75, 0.3],
    [0.5, 0.7],
  ]) {
    s += circle(cx, cy, 0.18);
  }
  return s;
}
function equipmentRack(): string {
  let s = rect(0.03, 0.03, 0.94, 0.94);
  for (const x of [0.2, 0.4, 0.6, 0.8]) s += line(x, 0.03, x, 0.97);
  for (const y of [0.3, 0.6]) s += line(0.03, y, 0.97, y);
  return s;
}
function genericBox(): string {
  return rect(0.06, 0.06, 0.88, 0.88, 0.04) + line(0.06, 0.06, 0.94, 0.94) + line(0.94, 0.06, 0.06, 0.94);
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
  washing_machine: washingMachine,
  planters: planters,
  equipment_rack: equipmentRack,
};

export function furnitureIconMarkup(type: string): string {
  const fn = ICONS[type] ?? genericBox;
  return fn();
}
