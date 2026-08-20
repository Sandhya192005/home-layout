/** Site-level icons (landscaping, vehicles) drawn in a 0..1 unit square,
 * same convention as furnitureIcons.ts — caller wraps in a translate+scale
 * transform to place them at real coordinates. */

const INK = `stroke="var(--ink-soft)" vector-effect="non-scaling-stroke"`;

export function treeIconMarkup(seed: number): string {
  // a simple canopy blob + trunk dot, varied slightly by seed so a cluster
  // of trees doesn't look like stamped copies
  const wobble = (seed % 5) * 0.02 - 0.04;
  return (
    `<circle cx="${0.5 + wobble}" cy="0.42" r="0.4" fill="var(--garden-canopy)" ${INK} />` +
    `<circle cx="${0.5 - wobble}" cy="0.36" r="0.3" fill="var(--garden-canopy)" ${INK} />` +
    `<circle cx="0.5" cy="0.5" r="0.05" fill="var(--ink-soft)" />`
  );
}

export function carIconMarkup(): string {
  return (
    `<rect x="0.1" y="0.03" width="0.8" height="0.94" rx="0.14" fill="var(--surface)" ${INK} />` +
    `<rect x="0.18" y="0.16" width="0.64" height="0.3" rx="0.06" fill="var(--room-wet)" ${INK} />` +
    `<line x1="0.1" y1="0.55" x2="0.9" y2="0.55" ${INK} />` +
    `<circle cx="0.14" cy="0.22" r="0.05" fill="var(--ink-soft)" />` +
    `<circle cx="0.86" cy="0.22" r="0.05" fill="var(--ink-soft)" />` +
    `<circle cx="0.14" cy="0.78" r="0.05" fill="var(--ink-soft)" />` +
    `<circle cx="0.86" cy="0.78" r="0.05" fill="var(--ink-soft)" />`
  );
}

export function bikeIconMarkup(): string {
  return (
    `<circle cx="0.5" cy="0.22" r="0.16" fill="none" ${INK} />` +
    `<circle cx="0.5" cy="0.78" r="0.16" fill="none" ${INK} />` +
    `<line x1="0.5" y1="0.38" x2="0.5" y2="0.62" ${INK} />`
  );
}
