// Mirrors backend/app/schemas/*.py

export interface AuditFields {
  created_at: string;
  created_by: number | null;
  updated_at: string;
  updated_by: number | null;
  deleted_at: string | null;
  deleted_by: number | null;
  is_active: boolean;
}

export interface User extends AuditFields {
  id: number;
  email: string;
  full_name: string;
}

export interface Project extends AuditFields {
  id: number;
  owner_id: number;
  name: string;
  description: string | null;
  status: string;
}

export type Facing = "north" | "south" | "east" | "west";
export type FloorType = "duplex" | "independent";
export type CompoundWallStyle = "none" | "wall" | "fence";
export type GateStyle = "swing" | "sliding";

export const ADDITIONAL_ROOM_TYPES = [
  "home_office",
  "servant_room",
  "store_room",
  "guest_room",
  "gym",
  "library",
] as const;
export type AdditionalRoomType = (typeof ADDITIONAL_ROOM_TYPES)[number];

export interface RequirementInput {
  plot_length: number;
  plot_width: number;
  facing: Facing;
  family_members: number;
  bedrooms: number;
  bathrooms: number;
  has_living_room: boolean;
  has_dining_room: boolean;
  has_pooja_room: boolean;
  has_study_room: boolean;
  has_utility_room: boolean;
  has_veranda: boolean;
  has_foyer: boolean;
  balconies: number;
  cars: number;
  two_wheelers: number;
  compound_wall_style: CompoundWallStyle;
  gate_style: GateStyle;
  floors: number;
  floor_type: FloorType;
  budget: number;
  vastu_compliant: boolean;
  wheelchair_accessible: boolean;
  additional_rooms: AdditionalRoomType[];
  other_requirements: string | null;
}

export interface Requirement extends RequirementInput, AuditFields {
  id: number;
  project_id: number;
}

export interface FurnitureItem {
  type: string;
  x: number;
  y: number;
  w: number;
  l: number;
  rotation: number;
}

export interface RoomData {
  id: string;
  type: string;
  label: string;
  zone: string;
  x: number;
  y: number;
  width: number;
  length: number;
  area: number;
  below_min_size: boolean;
  furniture: FurnitureItem[];
  attached_bathroom_id?: string | null;
  attached_to?: string | null;
  has_window?: boolean;
}

export interface WallData {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  thickness: number;
  type: "exterior" | "interior";
  side?: string;
  between?: [string, string];
}

export interface DoorData {
  type: "main_entrance" | "internal";
  room_id: string;
  wall?: string;
  connects_to?: string;
  width: number;
  center_x: number;
  center_y: number;
}

export interface WindowData {
  room_id: string;
  wall: string;
  width: number;
  center_x: number;
  center_y: number;
}

export interface ParkingData {
  x: number;
  y: number;
  width: number;
  length: number;
  capacity_cars: number;
  capacity_two_wheelers: number;
}

export interface RampData {
  x: number;
  y: number;
  width: number;
  length: number;
  side: "north" | "south" | "east" | "west";
}

export interface MainGateData {
  x: number;
  y: number;
  width: number;
  side: "north" | "south" | "east" | "west";
}

export interface RoomRectUpdate {
  x: number;
  y: number;
  width: number;
  length: number;
}

export interface RoomLayoutUpdateInput {
  floor_number: number;
  rooms: Record<string, RoomRectUpdate>;
}

export interface ParkingLayoutUpdateInput {
  floor_number: number;
  parking: RoomRectUpdate;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatRequestInput {
  messages: ChatMessage[];
  project_id?: number | null;
}

export interface ChatResponse {
  reply: string;
}

export interface FloorData {
  floor_number: number;
  label: string;
  outline: { x: number; y: number; width: number; length: number };
  rooms: RoomData[];
  walls: WallData[];
  doors: DoorData[];
  windows: WindowData[];
  parking: ParkingData | null;
  ramp: RampData | null;
  main_gate: MainGateData | null;
  has_staircase: boolean;
}

export interface CostEstimate {
  total_built_up_area: number;
  tier_estimates: Record<string, number>;
  recommended_tier: string;
  recommended_cost: number;
  within_budget: boolean;
}

export interface BoqEstimate {
  cement_bags: number;
  steel_kg: number;
  bricks: number;
  sand_cft: number;
  aggregate_cft: number;
  paint_liters: number;
}

export interface ConstructionTimeline {
  phases_weeks: Record<string, number>;
  total_weeks: number;
  total_months: number;
}

export interface FarEstimate {
  far: number;
  max_far: number;
  exceeds_typical_limit: boolean;
}

export interface PlanData {
  meta: {
    plot_length: number;
    plot_width: number;
    unit: string;
    facing: Facing;
    floors: number;
    vastu_compliant: boolean;
    compound_wall_style?: CompoundWallStyle;
    gate_style?: GateStyle;
    total_built_up_area: number;
    buildable_footprint: { x: number; y: number; width: number; length: number };
    cost_estimate?: CostEstimate;
    boq?: BoqEstimate;
    construction_timeline?: ConstructionTimeline;
    far?: FarEstimate;
  };
  floors: FloorData[];
}

export interface FloorPlan extends AuditFields {
  id: number;
  project_id: number;
  requirement_id: number;
  version: number;
  status: string;
  plan_data: PlanData;
  total_built_up_area: number;
  estimated_cost: number;
}

export interface FloorPlanGenerateResponse {
  floor_plan: FloorPlan;
  warnings: string[];
}

export interface AttachedBathroomResponse {
  floor_plan: FloorPlan;
  warnings: string[];
}

export interface FurnitureLayoutUpdateInput {
  floor_number: number;
  furniture_by_room: Record<string, FurnitureItem[]>;
}

export interface FloorPlanShare extends AuditFields {
  id: number;
  floor_plan_id: number;
  token: string;
}

export interface PublicFloorPlan {
  project_name: string;
  version: number;
  status: string;
  plan_data: PlanData;
  total_built_up_area: number;
  estimated_cost: number;
}
