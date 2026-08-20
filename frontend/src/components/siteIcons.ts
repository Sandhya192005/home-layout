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
  // alternate body color per car so a multi-car parking row reads clearly against the pale pad
  const bodyColor = typeof label === "number" && label % 2 === 0 ? "var(--car-blue)" : "var(--car-red)";
  return (
    // body: tapered hood up front, squared-off trunk at the rear
    `<path d="M 0.22 0.05 Q 0.5 -0.01 0.78 0.05 L 0.9 0.27 L 0.9 0.85 Q 0.9 0.96 0.79 0.96 L 0.21 0.96 Q 0.1 0.96 0.1 0.85 L 0.1 0.27 Z" fill="${bodyColor}" ${INK} />` +
    `<rect x="0.2" y="0.14" width="0.6" height="0.17" rx="0.05" fill="var(--water)" ${INK} />` + // windshield
    `<rect x="0.2" y="0.7" width="0.6" height="0.15" rx="0.05" fill="var(--water)" ${INK} />` + // rear window
    `<rect x="0.02" y="0.24" width="0.09" height="0.05" rx="0.02" fill="var(--ink)" />` + // mirrors
    `<rect x="0.89" y="0.24" width="0.09" height="0.05" rx="0.02" fill="var(--ink)" />` +
    `<rect x="0.03" y="0.15" width="0.07" height="0.17" rx="0.03" fill="var(--ink)" />` + // wheels
    `<rect x="0.9" y="0.15" width="0.07" height="0.17" rx="0.03" fill="var(--ink)" />` +
    `<rect x="0.03" y="0.68" width="0.07" height="0.17" rx="0.03" fill="var(--ink)" />` +
    `<rect x="0.9" y="0.68" width="0.07" height="0.17" rx="0.03" fill="var(--ink)" />` +
    numberLabel
  );
}

const BIKE = `stroke="var(--bike-body)" vector-effect="non-scaling-stroke"`;

export function bikeIconMarkup(): string {
  return (
    `<circle cx="0.5" cy="0.5" r="0.46" fill="var(--surface)" ${INK} />` + // pad so the thin frame reads against grass/pavers
    `<circle cx="0.5" cy="0.2" r="0.16" fill="none" ${BIKE} />` + // front wheel
    `<circle cx="0.5" cy="0.8" r="0.16" fill="none" ${BIKE} />` + // rear wheel
    `<circle cx="0.5" cy="0.2" r="0.045" fill="var(--bike-body)" />` +
    `<circle cx="0.5" cy="0.8" r="0.045" fill="var(--bike-body)" />` +
    `<line x1="0.5" y1="0.34" x2="0.5" y2="0.66" ${BIKE} />` +
    `<line x1="0.5" y1="0.42" x2="0.36" y2="0.66" ${BIKE} />` +
    `<line x1="0.5" y1="0.42" x2="0.64" y2="0.66" ${BIKE} />` +
    `<line x1="0.34" y1="0.1" x2="0.66" y2="0.1" ${BIKE} />` + // handlebar
    `<line x1="0.4" y1="0.9" x2="0.6" y2="0.9" ${BIKE} />` // seat
  );
}
