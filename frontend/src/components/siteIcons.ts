/** Site-level icons (landscaping, vehicles) drawn in a 0..1 unit square,
 * same convention as furnitureIcons.ts — caller wraps in a translate+scale
 * transform to place them at real coordinates. */

const INK = `stroke="var(--ink-soft)" vector-effect="non-scaling-stroke"`;

export function treeIconMarkup(seed: number): string {
  // a layered canopy of 3-4 overlapping blobs in varying greens + trunk,
  // varied by seed so a cluster of trees doesn't look like stamped copies
  const wobble = (seed % 5) * 0.03 - 0.06;
  const wobble2 = (seed % 3) * 0.04 - 0.04;
  return (
    `<circle cx="${0.52 + wobble}" cy="0.46" r="0.36" fill="var(--garden-canopy-dark)" ${INK} />` +
    `<circle cx="${0.32 - wobble2}" cy="0.4" r="0.3" fill="var(--garden-canopy)" ${INK} />` +
    `<circle cx="${0.68 + wobble2}" cy="0.38" r="0.28" fill="var(--garden-canopy)" ${INK} />` +
    `<circle cx="0.5" cy="0.3" r="0.24" fill="var(--garden-canopy-light)" ${INK} />` +
    `<line x1="0.5" y1="0.62" x2="0.5" y2="0.94" stroke="var(--wood-dark)" stroke-width="0.06" vector-effect="non-scaling-stroke" />`
  );
}

export function shrubIconMarkup(seed: number): string {
  // a smaller, single-blob bush for variety among the taller trees
  const wobble = (seed % 4) * 0.03 - 0.045;
  return (
    `<circle cx="${0.5 + wobble}" cy="0.55" r="0.4" fill="var(--garden-canopy)" ${INK} />` +
    `<circle cx="${0.5 - wobble}" cy="0.48" r="0.3" fill="var(--garden-canopy-light)" ${INK} />`
  );
}

export function carIconMarkup(label?: string | number): string {
  const numberLabel = label !== undefined
    ? `<text x="0.5" y="0.55" text-anchor="middle" font-size="0.26" fill="var(--accent-ink)" font-family="var(--font-mono)" font-weight="700">${label}</text>`
    : "";
  return (
    // body: tapered hood up front, squared-off trunk at the rear
    `<path d="M 0.22 0.05 Q 0.5 -0.01 0.78 0.05 L 0.9 0.27 L 0.9 0.85 Q 0.9 0.96 0.79 0.96 L 0.21 0.96 Q 0.1 0.96 0.1 0.85 L 0.1 0.27 Z" fill="var(--car-black)" ${INK} />` +
    `<rect x="0.2" y="0.14" width="0.6" height="0.17" rx="0.05" fill="var(--water)" ${INK} />` + // windshield
    `<rect x="0.2" y="0.7" width="0.6" height="0.15" rx="0.05" fill="var(--water)" ${INK} />` + // rear window
    `<rect x="0.02" y="0.24" width="0.09" height="0.05" rx="0.02" fill="var(--ink-faint)" />` + // mirrors
    `<rect x="0.89" y="0.24" width="0.09" height="0.05" rx="0.02" fill="var(--ink-faint)" />` +
    `<rect x="0.03" y="0.15" width="0.07" height="0.17" rx="0.03" fill="var(--ink-faint)" />` + // wheels
    `<rect x="0.9" y="0.15" width="0.07" height="0.17" rx="0.03" fill="var(--ink-faint)" />` +
    `<rect x="0.03" y="0.68" width="0.07" height="0.17" rx="0.03" fill="var(--ink-faint)" />` +
    `<rect x="0.9" y="0.68" width="0.07" height="0.17" rx="0.03" fill="var(--ink-faint)" />` +
    numberLabel
  );
}

export function bikeIconMarkup(): string {
  const body = `fill="var(--bike-body)" ${INK}`;
  return (
    `<circle cx="0.5" cy="0.5" r="0.47" fill="var(--surface)" ${INK} />` + // pad so the solid shape reads against grass/pavers
    // wheels: solid filled discs, not thin outlines, so they carry the same visual weight as the car
    `<circle cx="0.5" cy="0.21" r="0.18" ${body} />` +
    `<circle cx="0.5" cy="0.79" r="0.18" ${body} />` +
    `<circle cx="0.5" cy="0.21" r="0.06" fill="var(--surface)" />` + // hubs
    `<circle cx="0.5" cy="0.79" r="0.06" fill="var(--surface)" />` +
    // frame: a solid tapered body connecting the two wheels, like the car's body panel
    `<path d="M 0.43 0.32 L 0.57 0.32 L 0.61 0.68 L 0.39 0.68 Z" ${body} />` +
    `<rect x="0.32" y="0.06" width="0.36" height="0.07" rx="0.03" ${body} />` + // handlebar
    `<rect x="0.37" y="0.87" width="0.26" height="0.07" rx="0.03" ${body} />` // seat
  );
}
