import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { PlanData } from "../api/types";

const FLOOR_HEIGHT = 10;
const SLAB_THICKNESS = 0.6;
const ROOF_OVERHANG = 1;
const ROOF_THICKNESS = 0.8;

const ROOM_COLOR: Record<string, number> = {
  living_room: 0xdce8f5,
  dining_room: 0xf5e6d3,
  kitchen: 0xf7d9c4,
  master_bedroom: 0xe3d9f0,
  bedroom: 0xe3d9f0,
  guest_room: 0xe3d9f0,
  bathroom: 0xcfe8e2,
  accessible_bathroom: 0xcfe8e2,
  utility: 0xd9d9d9,
  pooja_room: 0xf9edc9,
  study_room: 0xd7e8d4,
  foyer: 0xe6e0d4,
  veranda: 0xe6e0d4,
  staircase: 0xb8b8b8,
  home_office: 0xd7e8d4,
  servant_room: 0xe0e0e0,
  store_room: 0xe0e0e0,
  gym: 0xd7e8d4,
  library: 0xd7e8d4,
};
const DEFAULT_ROOM_COLOR = 0xe8e8e8;
const WALL_COLOR = 0xf3efe7;
const SLAB_COLOR = 0xb9b0a0;
const ROOF_COLOR = 0x8a5a44;
const GROUND_COLOR = 0xdcd3c0;
const PARKING_COLOR = 0xa9a9a9;
const WINDOW_COLOR = 0x6fa8dc;
const DOOR_COLOR = 0x8b5e34;

const WOOD = 0x9c7b52;
const WOOD_DARK = 0x6b4d34;
const FABRIC = 0x8a6b74;
const FABRIC_DARK = 0x6d525a;
const BEDDING = 0xf2ede2;
const CERAMIC = 0xf5f5f2;
const METAL = 0xc7cbd1;
const DARK_METAL = 0x2e2e2e;
const GLASS = 0xbcd7e6;
const GOLD = 0xd4af37;
const PLANT_GREEN = 0x4f7d43;
const POT_COLOR = 0xb5651d;

interface MatFinish {
  roughness?: number;
  metalness?: number;
}

function addBox(
  group: THREE.Group,
  w: number,
  h: number,
  d: number,
  color: number,
  cx = 0,
  cy = 0,
  cz = 0,
  opacity = 1,
  finish?: MatFinish
): THREE.Mesh {
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(Math.max(w, 0.02), Math.max(h, 0.02), Math.max(d, 0.02)),
    new THREE.MeshStandardMaterial({
      color,
      transparent: opacity < 1,
      opacity,
      roughness: finish?.roughness ?? 0.85,
      metalness: finish?.metalness ?? 0.05,
    })
  );
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  mesh.position.set(cx, cy, cz);
  group.add(mesh);
  return mesh;
}

function addCylinder(
  group: THREE.Group,
  rTop: number,
  rBottom: number,
  h: number,
  color: number,
  cx = 0,
  cy = 0,
  cz = 0,
  finish?: MatFinish
): THREE.Mesh {
  const mesh = new THREE.Mesh(
    new THREE.CylinderGeometry(Math.max(rTop, 0.01), Math.max(rBottom, 0.01), Math.max(h, 0.02), 16),
    new THREE.MeshStandardMaterial({
      color,
      roughness: finish?.roughness ?? 0.85,
      metalness: finish?.metalness ?? 0.05,
    })
  );
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  mesh.position.set(cx, cy, cz);
  group.add(mesh);
  return mesh;
}

/** Builds a stylized low-poly furniture piece from simple primitives, sized
 * to the item's real footprint (w = along x, l = along z), sitting on the
 * floor (y=0) and centered on the origin in x/z so the caller can position
 * it at the item's center and rotate the whole group as one unit. */
function buildFurnitureMesh(type: string, w: number, l: number): THREE.Group {
  const group = new THREE.Group();

  function fourLegs(h: number, insetX: number, insetZ: number, color = WOOD_DARK) {
    const legR = 0.06;
    for (const x of [-w / 2 + insetX, w / 2 - insetX]) {
      for (const z of [-l / 2 + insetZ, l / 2 - insetZ]) {
        addCylinder(group, legR, legR, h, color, x, h / 2, z);
      }
    }
  }

  switch (type) {
    case "sofa_set": {
      const backT = Math.min(l * 0.22, 0.6);
      const armW = Math.min(w * 0.14, 0.5);
      addBox(group, w, 1.0, l, FABRIC, 0, 0.5, 0);
      addBox(group, w, 2.0, backT, FABRIC_DARK, 0, 1.0, -l / 2 + backT / 2);
      addBox(group, armW, 1.6, l, FABRIC_DARK, -w / 2 + armW / 2, 0.8, 0);
      addBox(group, armW, 1.6, l, FABRIC_DARK, w / 2 - armW / 2, 0.8, 0);
      break;
    }
    case "chair": {
      addBox(group, w * 0.85, 0.15, l * 0.85, WOOD, 0, 0.85, 0);
      addBox(group, w * 0.85, 0.9, Math.min(l * 0.12, 0.15), WOOD_DARK, 0, 1.3, -l / 2 + 0.08);
      fourLegs(0.78, w * 0.1, l * 0.1);
      break;
    }
    case "center_table":
    case "study_table":
    case "desk": {
      const h = type === "center_table" ? 1.1 : 1.25;
      addBox(group, w, 0.12, l, WOOD, 0, h - 0.06, 0);
      fourLegs(h - 0.12, Math.min(w * 0.08, 0.3), Math.min(l * 0.08, 0.3));
      if (type !== "center_table") {
        addBox(group, w * 0.3, 0.5, l * 0.7, WOOD_DARK, w / 2 - w * 0.18, h - 0.12 - 0.25, 0);
      }
      break;
    }
    case "dining_table_6": {
      const insetX = Math.min(w * 0.2, 1);
      const insetZ = Math.min(l * 0.2, 1);
      const tableW = Math.max(w - insetX * 1.7, w * 0.4);
      const tableL = Math.max(l - insetZ * 1.7, l * 0.4);
      addBox(group, tableW, 0.14, tableL, WOOD, 0, 1.36, 0);
      const legR = 0.06;
      for (const x of [-tableW / 2 + 0.15, tableW / 2 - 0.15]) {
        for (const z of [-tableL / 2 + 0.15, tableL / 2 - 0.15]) {
          addCylinder(group, legR, legR, 1.29, WOOD_DARK, x, 1.29 / 2, z);
        }
      }

      const chairSize = Math.min(w, l) * 0.28;
      function miniChair(faceDeg: number, cx: number, cz: number) {
        const c = new THREE.Group();
        const seatH = 0.8;
        addBox(c, chairSize, 0.12, chairSize, WOOD, 0, seatH, 0);
        addBox(c, chairSize, 0.7, Math.min(chairSize * 0.18, 0.1), WOOD_DARK, 0, seatH + 0.35, -chairSize / 2 + 0.04);
        const legR2 = 0.04;
        for (const x of [-chairSize / 2 + 0.06, chairSize / 2 - 0.06]) {
          for (const z of [-chairSize / 2 + 0.06, chairSize / 2 - 0.06]) {
            addCylinder(c, legR2, legR2, seatH - 0.06, WOOD_DARK, x, (seatH - 0.06) / 2, z);
          }
        }
        c.rotation.y = THREE.MathUtils.degToRad(faceDeg);
        c.position.set(cx, 0, cz);
        group.add(c);
      }
      const zEdge = l / 2 - insetZ * 0.5;
      const xEdge = w / 2 - insetX * 0.5;
      miniChair(0, -w * 0.22, -zEdge);
      miniChair(0, w * 0.22, -zEdge);
      miniChair(180, -w * 0.22, zEdge);
      miniChair(180, w * 0.22, zEdge);
      miniChair(90, -xEdge, 0);
      miniChair(-90, xEdge, 0);
      break;
    }
    case "tv_unit": {
      addBox(group, w, 1.0, l, WOOD_DARK, 0, 0.5, 0);
      const screenW = w * 0.75;
      const screenH = screenW * 0.55;
      addBox(group, screenW, screenH, 0.08, DARK_METAL, 0, 1.0 + screenH / 2 + 0.1, -l / 2 + 0.1);
      break;
    }
    case "bed_king":
    case "bed_queen":
    case "bed_single": {
      addBox(group, w, 0.25, l, WOOD_DARK, 0, 0.125, 0);
      addBox(group, w * 0.94, 0.35, l * 0.86, BEDDING, 0, 0.42, l * 0.02);
      addBox(group, w, 1.5, 0.15, WOOD_DARK, 0, 0.75, -l / 2 + 0.075);
      addBox(group, w * 0.28, 0.15, l * 0.16, 0xffffff, -w * 0.2, 0.65, -l / 2 + l * 0.14);
      addBox(group, w * 0.28, 0.15, l * 0.16, 0xffffff, w * 0.2, 0.65, -l / 2 + l * 0.14);
      break;
    }
    case "wardrobe": {
      addBox(group, w, 6.5, l, WOOD, 0, 3.25, 0);
      addBox(group, 0.05, 6.3, l + 0.02, WOOD_DARK, 0, 3.25, 0);
      addCylinder(group, 0.05, 0.05, 0.3, METAL, -0.1, 3.25, l / 2 - 0.05);
      addCylinder(group, 0.05, 0.05, 0.3, METAL, 0.1, 3.25, l / 2 - 0.05);
      break;
    }
    case "dresser": {
      addBox(group, w, 2.6, l, WOOD, 0, 1.3, 0);
      addBox(group, w * 0.5, 2.0, 0.06, GLASS, 0, 2.6 + 1.0, -l / 2 + 0.03, 0.6);
      break;
    }
    case "bookshelf":
    case "shelving":
    case "equipment_rack": {
      const color = type === "equipment_rack" ? METAL : WOOD;
      const darkColor = type === "equipment_rack" ? DARK_METAL : WOOD_DARK;
      const h = 6;
      addBox(group, w, h, l, color, 0, h / 2, 0);
      const shelves = 4;
      for (let i = 1; i <= shelves; i++) {
        addBox(group, w, 0.08, l, darkColor, 0, (h / (shelves + 1)) * i, 0);
      }
      break;
    }
    case "l_shape_counter": {
      addBox(group, w, 3, l, 0xd8d2c4, 0, 1.5, 0);
      addBox(group, w, 0.12, l, 0xffffff, 0, 3.06, 0, 1, { roughness: 0.2, metalness: 0.1 });
      break;
    }
    case "sink":
    case "wash_sink":
    case "wash_basin": {
      const r = Math.min(w, l) / 2;
      const finish = { roughness: 0.2, metalness: 0.05 };
      addCylinder(group, r * 0.6, r * 0.4, 2.2, CERAMIC, 0, 1.1, 0, finish);
      addBox(group, w * 0.9, 0.3, l * 0.9, CERAMIC, 0, 2.35, 0, 1, finish);
      break;
    }
    case "stove": {
      addBox(group, w, 2.6, l, DARK_METAL, 0, 1.3, 0, 1, { roughness: 0.4, metalness: 0.5 });
      for (const x of [-w * 0.22, w * 0.22]) {
        for (const z of [-l * 0.22, l * 0.22]) {
          addCylinder(group, 0.18, 0.18, 0.06, 0x111111, x, 2.63, z, { roughness: 0.4, metalness: 0.6 });
        }
      }
      break;
    }
    case "refrigerator": {
      addBox(group, w, 5.5, l, METAL, 0, 2.75, 0, 1, { roughness: 0.3, metalness: 0.6 });
      addBox(group, 0.08, 3.5, 0.08, DARK_METAL, w / 2 - 0.15, 3.0, l / 2 - 0.1);
      break;
    }
    case "washing_machine": {
      addBox(group, w, 3.2, l, 0xe8e8e8, 0, 1.6, 0, 1, { roughness: 0.35, metalness: 0.4 });
      const doorR = Math.min(w, l) * 0.3;
      const door = addCylinder(group, doorR, doorR, 0.06, DARK_METAL, 0, 1.6, l / 2 - 0.03, {
        roughness: 0.2,
        metalness: 0.3,
      });
      door.rotation.x = Math.PI / 2;
      break;
    }
    case "mandir_unit": {
      addBox(group, w, 0.6, l, WOOD, 0, 0.3, 0);
      addBox(group, w * 0.7, 2.5, l * 0.7, WOOD_DARK, 0, 0.6 + 1.25, 0);
      addCylinder(group, 0.01, w * 0.4, 0.6, GOLD, 0, 0.6 + 2.5 + 0.3, 0, { roughness: 0.3, metalness: 0.8 });
      break;
    }
    case "wc": {
      const finish = { roughness: 0.2, metalness: 0.05 };
      addBox(group, w * 0.7, 1.0, l * 0.6, CERAMIC, 0, 0.5, l * 0.05, 1, finish);
      addBox(group, w * 0.6, 0.9, l * 0.25, CERAMIC, 0, 1.45, -l / 2 + l * 0.125, 1, finish);
      break;
    }
    case "shower": {
      addBox(group, w, 0.1, l, CERAMIC, 0, 0.05, 0, 1, { roughness: 0.2, metalness: 0.05 });
      addBox(group, 0.04, 6.5, l, GLASS, -w / 2 + 0.02, 3.25, 0, 0.3, { roughness: 0.05, metalness: 0.1 });
      addBox(group, w, 6.5, 0.04, GLASS, 0, 3.25, -l / 2 + 0.02, 0.3, { roughness: 0.05, metalness: 0.1 });
      addCylinder(group, 0.08, 0.08, 0.3, METAL, -w / 2 + 0.2, 6.2, -l / 2 + 0.2, { roughness: 0.3, metalness: 0.7 });
      break;
    }
    case "grab_bar": {
      const barLen = Math.max(w, l) * 0.85;
      const bar = addCylinder(group, 0.08, 0.08, barLen, METAL, 0, 2.5, 0);
      if (l > w) bar.rotation.x = Math.PI / 2;
      else bar.rotation.z = Math.PI / 2;
      break;
    }
    case "planters": {
      const r = Math.min(w, l) / 2;
      addCylinder(group, r * 0.7, r * 0.95, 0.9, POT_COLOR, 0, 0.45);
      addCylinder(group, 0.02, r * 0.75, 1.1, PLANT_GREEN, 0, 0.9 + 0.55);
      break;
    }
    default: {
      addBox(group, w, 2, l, WOOD, 0, 1, 0);
    }
  }

  return group;
}

// Leads with a clean white/pearl finish (the common real-world case, and
// what a single-car driveway should default to) then cycles through a few
// other realistic showroom colors for lots with more than one car -- swapped
// out from the earlier red/green/tan palette, which read as toy-like.
const CAR_COLORS = [0xf1f0ec, 0x232323, 0xb7bcc2, 0x2f4a72, 0x7a1f1f, 0xd9d3c4];

function addWheel(group: THREE.Group, r: number, thickness: number, cx: number, cy: number, cz: number): void {
  const mesh = new THREE.Mesh(
    new THREE.CylinderGeometry(r, r, thickness, 14),
    new THREE.MeshStandardMaterial({ color: 0x1c1c1c, roughness: 0.85, metalness: 0.1 })
  );
  mesh.rotation.z = Math.PI / 2;
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  mesh.position.set(cx, cy, cz);
  group.add(mesh);
}

/** Builds a car with a stepped silhouette (hood / greenhouse cabin / trunk
 * exposed on a lower chassis, plus bumpers, lights and mirrors) instead of a
 * single box, so it actually reads as a car. Local x = side-to-side (w),
 * local z = front-to-back (h), front at +z. */
function buildCarMesh(w: number, h: number, colorIndex: number): THREE.Group {
  const group = new THREE.Group();
  const color = CAR_COLORS[colorIndex % CAR_COLORS.length];
  const paint = { roughness: 0.35, metalness: 0.45 };
  const chassisW = w * 0.86;
  const chassisH = 0.55;
  const chassisL = h * 0.88;
  const bumperH = 0.3;
  const bumperLen = h * 0.06;

  // Main hull: doors, hood sides and trunk sides all live in this one box.
  addBox(group, chassisW, chassisH, chassisL, color, 0, chassisH / 2, 0, 1, paint);
  // Front/rear bumpers step down and out slightly from the hull.
  addBox(group, chassisW * 0.94, bumperH, bumperLen, 0x2c2c2c, 0, bumperH / 2, h / 2 - bumperLen / 2, 1, {
    roughness: 0.5,
    metalness: 0.2,
  });
  addBox(group, chassisW * 0.94, bumperH, bumperLen, 0x2c2c2c, 0, bumperH / 2, -h / 2 + bumperLen / 2, 1, {
    roughness: 0.5,
    metalness: 0.2,
  });
  // Greenhouse cabin: narrower and set back from center, leaving hood in
  // front and trunk behind exposed on the chassis top -- this is what makes
  // the silhouette actually read as a car instead of a loaf.
  const cabinW = chassisW * 0.72;
  const cabinH = 0.55;
  const cabinL = chassisL * 0.46;
  const cabinCz = -h * 0.04;
  addBox(group, cabinW, 0.06, cabinL, DARK_METAL, 0, chassisH + 0.03, cabinCz, 1, { roughness: 0.4 });
  addBox(group, cabinW * 0.94, cabinH - 0.06, cabinL * 0.92, 0xb9ccd6, 0, chassisH + 0.06 + (cabinH - 0.06) / 2, cabinCz, 0.5, {
    roughness: 0.08,
    metalness: 0.25,
  });
  // Side mirrors.
  for (const x of [-cabinW / 2 - 0.08, cabinW / 2 + 0.08]) {
    addBox(group, 0.14, 0.1, 0.16, color, x, chassisH + cabinH * 0.55, cabinCz + cabinL * 0.35, 1, paint);
  }
  // Head/tail lights set into the bumpers.
  addBox(group, chassisW * 0.32, 0.12, 0.05, 0xfff6d8, -chassisW * 0.28, bumperH * 0.7, h / 2 - 0.02, 1, {
    roughness: 0.15,
    metalness: 0.3,
  });
  addBox(group, chassisW * 0.32, 0.12, 0.05, 0xfff6d8, chassisW * 0.28, bumperH * 0.7, h / 2 - 0.02, 1, {
    roughness: 0.15,
    metalness: 0.3,
  });
  addBox(group, chassisW * 0.32, 0.12, 0.05, 0xa32020, -chassisW * 0.28, bumperH * 0.7, -h / 2 + 0.02);
  addBox(group, chassisW * 0.32, 0.12, 0.05, 0xa32020, chassisW * 0.28, bumperH * 0.7, -h / 2 + 0.02);

  const wheelR = Math.min(w, h) * 0.16;
  const wheelT = w * 0.1;
  for (const x of [-chassisW / 2 + wheelR * 0.3, chassisW / 2 - wheelR * 0.3]) {
    for (const z of [-chassisL / 2 + wheelR * 1.2, chassisL / 2 - wheelR * 1.2]) {
      addWheel(group, wheelR, wheelT, x, wheelR, z);
    }
  }
  return group;
}

/** Builds a two-wheeler with a fuel tank, engine block, angled front fork and
 * head/tail lights instead of a single frame block. Local x = side-to-side
 * (w, narrow), local z = front-to-back (h, long), front at +z. */
function buildBikeMesh(w: number, h: number): THREE.Group {
  const group = new THREE.Group();
  const wheelR = Math.min(w, h) * 0.22;
  const wheelT = w * 0.32;
  const frontZ = h / 2 - wheelR * 1.2;
  const rearZ = -h / 2 + wheelR * 1.2;
  addWheel(group, wheelR, wheelT, 0, wheelR, frontZ);
  addWheel(group, wheelR, wheelT, 0, wheelR, rearZ);

  const rideH = wheelR + 0.1;
  addBox(group, w * 0.14, 0.14, h * 0.5, DARK_METAL, 0, rideH, -h * 0.02, 1, { roughness: 0.3, metalness: 0.6 });
  addBox(group, w * 0.36, 0.3, h * 0.16, 0x1c1c1c, 0, rideH + 0.13, -h * 0.03, 1, { roughness: 0.4, metalness: 0.5 });
  addBox(group, w * 0.3, 0.16, h * 0.17, DARK_METAL, 0, rideH + 0.34, h * 0.06, 1, { roughness: 0.25, metalness: 0.5 });
  addBox(group, w * 0.42, 0.1, h * 0.24, 0x1c1c1c, 0, rideH + 0.42, -h * 0.22, 1, { roughness: 0.5 });

  const fork = addBox(group, 0.08, 0.5, 0.08, METAL, 0, rideH + 0.22, frontZ - wheelR * 0.5, 1, {
    roughness: 0.3,
    metalness: 0.7,
  });
  fork.rotation.x = -0.3;
  addBox(group, w * 0.55, 0.07, 0.05, DARK_METAL, 0, rideH + 0.46, frontZ - wheelR * 0.9);

  addBox(group, w * 0.28, 0.1, 0.05, 0xfff6d8, 0, rideH + 0.15, frontZ + 0.03, 1, { roughness: 0.15, metalness: 0.3 });
  addBox(group, w * 0.22, 0.08, 0.05, 0xa32020, 0, rideH + 0.4, rearZ - 0.03);
  return group;
}

function makeLabelSprite(text: string): THREE.Sprite {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d")!;
  const scale = 64;
  canvas.width = 512;
  canvas.height = 128;
  ctx.font = "bold 44px sans-serif";
  const metrics = ctx.measureText(text);
  canvas.width = Math.max(128, metrics.width + 40);
  ctx.font = "bold 44px sans-serif";
  ctx.fillStyle = "rgba(30, 26, 20, 0.85)";
  ctx.textBaseline = "middle";
  ctx.textAlign = "center";
  ctx.fillText(text, canvas.width / 2, canvas.height / 2);
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false });
  const sprite = new THREE.Sprite(material);
  const worldWidth = canvas.width / scale;
  const worldHeight = canvas.height / scale;
  sprite.scale.set(worldWidth, worldHeight, 1);
  return sprite;
}

export default function FloorPlan3DView({ plan }: { plan: PlanData }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [showRoof, setShowRoof] = useState(true);
  const [showFurniture, setShowFurniture] = useState(true);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    const skyCanvas = document.createElement("canvas");
    skyCanvas.width = 8;
    skyCanvas.height = 256;
    const skyCtx = skyCanvas.getContext("2d")!;
    const skyGrad = skyCtx.createLinearGradient(0, 0, 0, 256);
    skyGrad.addColorStop(0, "#bcd6ea");
    skyGrad.addColorStop(0.55, "#e8ecdf");
    skyGrad.addColorStop(1, "#f2f0ea");
    skyCtx.fillStyle = skyGrad;
    skyCtx.fillRect(0, 0, 8, 256);
    const skyTexture = new THREE.CanvasTexture(skyCanvas);
    scene.background = skyTexture;

    const plotW = plan.meta.plot_width;
    const plotL = plan.meta.plot_length;
    const centerX = plotW / 2;
    const centerZ = plotL / 2;
    const buildingHeight = plan.floors.length * FLOOR_HEIGHT;
    const diag = Math.sqrt(plotW * plotW + plotL * plotL);
    scene.fog = new THREE.Fog(0xeceadf, diag * 1.1, diag * 3.6);

    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, diag * 6 + 200);
    camera.position.set(centerX + diag * 0.7, buildingHeight + diag * 0.55, centerZ + diag * 0.9);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(centerX, buildingHeight / 3, centerZ);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 5;
    controls.maxDistance = diag * 4 + 100;
    controls.maxPolarAngle = Math.PI / 2 - 0.02;
    controls.update();

    scene.add(new THREE.AmbientLight(0xffffff, 0.4));
    const sun = new THREE.DirectionalLight(0xfff4e0, 1.2);
    sun.position.set(centerX + diag * 0.6, buildingHeight + diag * 0.8, centerZ - diag * 0.4);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    const shadowSpan = diag * 0.9 + buildingHeight;
    sun.shadow.camera.left = -shadowSpan;
    sun.shadow.camera.right = shadowSpan;
    sun.shadow.camera.top = shadowSpan;
    sun.shadow.camera.bottom = -shadowSpan;
    sun.shadow.camera.near = 1;
    sun.shadow.camera.far = diag * 3 + buildingHeight * 3;
    sun.shadow.bias = -0.0015;
    sun.target.position.set(centerX, 0, centerZ);
    scene.add(sun);
    scene.add(sun.target);
    scene.add(new THREE.HemisphereLight(0xcfe0f0, 0x8a8272, 0.3));

    // Ground / plot
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(plotW + 20, plotL + 20),
      new THREE.MeshStandardMaterial({ color: GROUND_COLOR, roughness: 1 })
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(centerX, -0.05, centerZ);
    ground.receiveShadow = true;
    scene.add(ground);

    const plotEdges = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.PlaneGeometry(plotW, plotL)),
      new THREE.LineBasicMaterial({ color: 0x9a9382 })
    );
    plotEdges.rotation.x = -Math.PI / 2;
    plotEdges.position.set(centerX, 0.01, centerZ);
    scene.add(plotEdges);

    for (const floor of plan.floors) {
      const baseY = floor.floor_number * FLOOR_HEIGHT;
      const o = floor.outline;

      // Floor slab
      const slab = new THREE.Mesh(
        new THREE.BoxGeometry(o.width, SLAB_THICKNESS, o.length),
        new THREE.MeshStandardMaterial({ color: SLAB_COLOR, roughness: 0.9 })
      );
      slab.position.set(o.x + o.width / 2, baseY - SLAB_THICKNESS / 2, o.y + o.length / 2);
      slab.castShadow = true;
      slab.receiveShadow = true;
      scene.add(slab);

      // Rooms: colored floor inset + label
      for (const room of floor.rooms) {
        const color = ROOM_COLOR[room.type] ?? DEFAULT_ROOM_COLOR;
        const inset = 0.15;
        const w = Math.max(room.width - inset * 2, 0.2);
        const l = Math.max(room.length - inset * 2, 0.2);
        const roomFloor = new THREE.Mesh(
          new THREE.BoxGeometry(w, 0.08, l),
          new THREE.MeshStandardMaterial({ color, roughness: 0.85 })
        );
        roomFloor.position.set(room.x + room.width / 2, baseY + 0.04, room.y + room.length / 2);
        roomFloor.receiveShadow = true;
        scene.add(roomFloor);

        if (Math.min(room.width, room.length) >= 4) {
          const label = makeLabelSprite(room.label);
          label.position.set(room.x + room.width / 2, baseY + 1.8, room.y + room.length / 2);
          scene.add(label);
        }

        if (showFurniture) {
          for (const item of room.furniture ?? []) {
            // item.w/item.l are the current (post-rotation) bounding-box dims --
            // e.g. a sofa rotated 90 deg has them swapped from its catalog size.
            // Un-swap back to the natural pose before building the shape, then
            // apply the rotation on top, matching the 2D icon transform exactly.
            const rotation = ((item.rotation % 360) + 360) % 360;
            const swapped = rotation % 180 !== 0;
            const naturalW = swapped ? item.l : item.w;
            const naturalL = swapped ? item.w : item.l;
            const piece = buildFurnitureMesh(item.type, naturalW, naturalL);
            piece.position.set(item.x + item.w / 2, baseY, item.y + item.l / 2);
            piece.rotation.y = -THREE.MathUtils.degToRad(item.rotation);
            scene.add(piece);
          }
        }
      }

      // Walls, extruded to floor height
      for (const wall of floor.walls) {
        const dx = wall.x2 - wall.x1;
        const dz = wall.y2 - wall.y1;
        const length = Math.hypot(dx, dz);
        if (length < 0.05) continue;
        const wallMesh = new THREE.Mesh(
          new THREE.BoxGeometry(length, FLOOR_HEIGHT, wall.thickness),
          new THREE.MeshStandardMaterial({ color: WALL_COLOR, transparent: true, opacity: 0.45, roughness: 0.9 })
        );
        wallMesh.position.set((wall.x1 + wall.x2) / 2, baseY + FLOOR_HEIGHT / 2, (wall.y1 + wall.y2) / 2);
        wallMesh.rotation.y = -Math.atan2(dz, dx);
        wallMesh.receiveShadow = true;
        scene.add(wallMesh);
      }

      // Windows: light-blue markers on exterior walls
      for (const win of floor.windows) {
        const room = floor.rooms.find((r) => r.id === win.room_id);
        if (!room) continue;
        const horizontal = win.wall === "north" || win.wall === "south";
        const marker = new THREE.Mesh(
          new THREE.BoxGeometry(horizontal ? win.width : 0.15, FLOOR_HEIGHT * 0.4, horizontal ? 0.15 : win.width),
          new THREE.MeshStandardMaterial({
            color: WINDOW_COLOR,
            transparent: true,
            opacity: 0.75,
            roughness: 0.1,
            metalness: 0.15,
          })
        );
        marker.position.set(win.center_x, baseY + FLOOR_HEIGHT * 0.55, win.center_y);
        scene.add(marker);
      }

      // Doors: brown markers at door centers
      for (const door of floor.doors) {
        const marker = new THREE.Mesh(
          new THREE.BoxGeometry(door.width * 0.6, FLOOR_HEIGHT * 0.55, 0.12),
          new THREE.MeshStandardMaterial({ color: DOOR_COLOR, roughness: 0.7 })
        );
        marker.position.set(door.center_x, baseY + FLOOR_HEIGHT * 0.28, door.center_y);
        marker.castShadow = true;
        scene.add(marker);
      }

      // Parking (ground floor only)
      if (floor.parking) {
        const p = floor.parking;
        const slabP = new THREE.Mesh(
          new THREE.BoxGeometry(p.width, 0.15, p.length),
          new THREE.MeshStandardMaterial({ color: PARKING_COLOR, roughness: 0.95 })
        );
        slabP.position.set(p.x + p.width / 2, 0.075, p.y + p.length / 2);
        slabP.receiveShadow = true;
        scene.add(slabP);

        if (showFurniture) {
          // Mirrors the 2D slot layout in buildFloorSvg exactly: slots run
          // along the parking rect's longer axis, each slotSize x cross.
          const horiz = p.width >= p.length;
          const totalSlots = p.capacity_cars + p.capacity_two_wheelers;
          if (totalSlots > 0) {
            const along = horiz ? p.width : p.length;
            const cross = horiz ? p.length : p.width;
            const slotSize = along / totalSlots;
            let idx = 0;
            const placeVehicle = (build: (fw: number, fl: number) => THREE.Group, marginFrac: number) => {
              const center = idx * slotSize + slotSize / 2;
              const footW = slotSize * (1 - marginFrac * 2);
              const footL = cross * (1 - marginFrac * 2);
              const cx = horiz ? p.x + center : p.x + cross / 2;
              const cz = horiz ? p.y + cross / 2 : p.y + center;
              const vehicle = build(footW, footL);
              vehicle.position.set(cx, 0.15, cz);
              if (!horiz) vehicle.rotation.y = -Math.PI / 2;
              scene.add(vehicle);
              idx++;
            };
            for (let i = 0; i < p.capacity_cars; i++) {
              placeVehicle((fw, fl) => buildCarMesh(fw, fl, i), 0.08);
            }
            for (let i = 0; i < p.capacity_two_wheelers; i++) {
              placeVehicle((fw, fl) => buildBikeMesh(fw, fl), 0.18);
            }
          }
        }
      }
    }

    // Gable roof on top of the highest floor: two sloped panels meeting at a
    // ridge (running along the building's longer axis) plus two triangular
    // end caps, instead of one flat slab -- reads much more like a real roof.
    if (showRoof) {
      const topOutline = plan.floors[plan.floors.length - 1].outline;
      const outerW = topOutline.width + ROOF_OVERHANG * 2;
      const outerL = topOutline.length + ROOF_OVERHANG * 2;
      const roofCx = topOutline.x + topOutline.width / 2;
      const roofCz = topOutline.y + topOutline.length / 2;
      const ridgeAlongX = outerW >= outerL;
      const span = (ridgeAlongX ? outerL : outerW) / 2;
      const ridgeHeight = THREE.MathUtils.clamp(span * 0.45, 2.5, 7);
      const slopeLen = Math.hypot(span, ridgeHeight);
      const pitchAngle = Math.atan2(ridgeHeight, span);
      const roofMat = new THREE.MeshStandardMaterial({ color: ROOF_COLOR, roughness: 0.75 });
      const capMat = new THREE.MeshStandardMaterial({ color: ROOF_COLOR, roughness: 0.8, side: THREE.DoubleSide });

      for (const sign of [-1, 1]) {
        const geomW = ridgeAlongX ? outerW : slopeLen;
        const geomL = ridgeAlongX ? slopeLen : outerW;
        const panel = new THREE.Mesh(new THREE.BoxGeometry(geomW, ROOF_THICKNESS, geomL), roofMat);
        const offset = (span / 2) * sign;
        if (ridgeAlongX) {
          panel.position.set(roofCx, buildingHeight + ridgeHeight / 2, roofCz + offset);
          panel.rotation.x = sign * pitchAngle;
        } else {
          panel.position.set(roofCx + offset, buildingHeight + ridgeHeight / 2, roofCz);
          panel.rotation.z = -sign * pitchAngle;
        }
        panel.castShadow = true;
        panel.receiveShadow = true;
        scene.add(panel);
      }

      const capShape = new THREE.Shape();
      capShape.moveTo(-span, 0);
      capShape.lineTo(span, 0);
      capShape.lineTo(0, ridgeHeight);
      capShape.closePath();
      for (const capOffset of [-1, 1]) {
        const cap = new THREE.Mesh(new THREE.ShapeGeometry(capShape), capMat);
        cap.castShadow = true;
        if (ridgeAlongX) {
          cap.rotation.y = Math.PI / 2;
          cap.position.set(roofCx + (outerW / 2) * capOffset, buildingHeight, roofCz);
        } else {
          cap.position.set(roofCx, buildingHeight, roofCz + (outerL / 2) * capOffset);
        }
        scene.add(cap);
      }
    }

    function resize() {
      if (!container) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      camera.aspect = w / Math.max(h, 1);
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    }
    resize();
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(container);

    let frameId = 0;
    function animate() {
      controls.update();
      renderer.render(scene, camera);
      frameId = requestAnimationFrame(animate);
    }
    animate();

    return () => {
      cancelAnimationFrame(frameId);
      resizeObserver.disconnect();
      controls.dispose();
      skyTexture.dispose();
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh || obj instanceof THREE.LineSegments) {
          obj.geometry.dispose();
          const mat = obj.material;
          if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
          else mat.dispose();
        } else if (obj instanceof THREE.Sprite) {
          obj.material.map?.dispose();
          obj.material.dispose();
        }
      });
      renderer.dispose();
      if (renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [plan, showRoof, showFurniture]);

  return (
    <div className="drawing-3d-outer">
      <div ref={containerRef} className="drawing-3d-wrap" />
      <div className="drawing-3d-toggles">
        <label className="drawing-3d-roof-toggle">
          <input type="checkbox" checked={showRoof} onChange={(e) => setShowRoof(e.target.checked)} />
          Show roof
        </label>
        <label className="drawing-3d-roof-toggle">
          <input type="checkbox" checked={showFurniture} onChange={(e) => setShowFurniture(e.target.checked)} />
          Show furniture
        </label>
      </div>
    </div>
  );
}
