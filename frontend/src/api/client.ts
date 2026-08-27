import type {
  FloorPlan,
  FloorPlanGenerateResponse,
  FloorPlanShare,
  FurnitureLayoutUpdateInput,
  Project,
  PublicFloorPlan,
  Requirement,
  RequirementInput,
  RoomLayoutUpdateInput,
  User,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL as string;
const TOKEN_KEY = "ahl_token";
const REFRESH_KEY = "ahl_refresh_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(accessToken: string | null, refreshToken: string | null) {
  setToken(accessToken);
  if (refreshToken) localStorage.setItem(REFRESH_KEY, refreshToken);
  else localStorage.removeItem(REFRESH_KEY);
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(extractMessage(detail));
    this.status = status;
    this.detail = detail;
  }
}

function extractMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    if (typeof d.detail === "string") return d.detail;
    if (d.detail && typeof d.detail === "object") {
      const inner = d.detail as Record<string, unknown>;
      if (Array.isArray(inner.errors)) return inner.errors.join(" "); // {errors: [...]} from validate_requirement
    }
    if (Array.isArray(d.detail)) {
      // FastAPI/pydantic default validation error shape
      return d.detail
        .map((e) => {
          const err = e as { loc?: unknown[]; msg?: string };
          const field = Array.isArray(err.loc) ? err.loc.slice(1).join(".") : "";
          return field ? `${field}: ${err.msg}` : err.msg ?? "Validation error";
        })
        .join(" ");
    }
  }
  return "Request failed";
}

let refreshInFlight: Promise<boolean> | null = null;

// Dedupes concurrent 401s into a single /auth/refresh call; returns whether
// the session was successfully refreshed.
async function refreshAccessToken(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const refreshToken = getRefreshToken();
      if (!refreshToken) return false;
      try {
        const res = await fetch(`${BASE_URL}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!res.ok) {
          setTokens(null, null);
          return false;
        }
        const data = (await res.json()) as { access_token: string; refresh_token: string };
        setTokens(data.access_token, data.refresh_token);
        return true;
      } catch {
        return false;
      }
    })().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

async function doFetch(path: string, method: string, headers: Record<string, string>, body: unknown) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const isJson = res.headers.get("content-type")?.includes("application/json");
  const data = res.status === 204 ? undefined : isJson ? await res.json() : await res.text();
  return { res, data };
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; auth?: boolean } = {}
): Promise<T> {
  const { method = "GET", body, auth = true } = options;
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let { res, data } = await doFetch(path, method, headers, body);

  // A stale/expired access token: try one silent refresh-and-retry before
  // surfacing the 401 (skip for the auth endpoints themselves to avoid loops).
  if (res.status === 401 && auth && !path.startsWith("/auth/")) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      const token = getToken();
      if (token) headers["Authorization"] = `Bearer ${token}`;
      ({ res, data } = await doFetch(path, method, headers, body));
    }
  }

  if (!res.ok) {
    throw new ApiError(res.status, data);
  }
  return data as T;
}

async function requestForm<T>(path: string, form: Record<string, string>): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams(form).toString(),
  });
  const data = await res.json();
  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}

// --- auth ---
export const api = {
  register: (input: { email: string; full_name: string; password: string }) =>
    request<User>("/auth/register", { method: "POST", body: input, auth: false }),

  login: (email: string, password: string) =>
    requestForm<{ access_token: string; refresh_token: string; token_type: string }>("/auth/login", {
      username: email,
      password,
    }),

  logout: (refreshToken: string) =>
    request<void>("/auth/logout", { method: "POST", body: { refresh_token: refreshToken }, auth: false }),

  me: () => request<User>("/auth/me"),

  // --- projects ---
  listProjects: () => request<Project[]>("/projects"),
  createProject: (input: { name: string; description?: string | null }) =>
    request<Project>("/projects", { method: "POST", body: input }),
  getProject: (id: number) => request<Project>(`/projects/${id}`),
  updateProject: (id: number, input: Partial<{ name: string; description: string | null; status: string }>) =>
    request<Project>(`/projects/${id}`, { method: "PUT", body: input }),
  deleteProject: (id: number) => request<void>(`/projects/${id}`, { method: "DELETE" }),

  // --- requirements ---
  listRequirements: (projectId: number) => request<Requirement[]>(`/projects/${projectId}/requirements`),
  latestRequirement: (projectId: number) => request<Requirement>(`/projects/${projectId}/requirements/latest`),
  submitRequirement: (projectId: number, input: RequirementInput) =>
    request<Requirement>(`/projects/${projectId}/requirements`, { method: "POST", body: input }),
  generatePlan: (projectId: number, requirementId: number) =>
    request<FloorPlanGenerateResponse>(`/projects/${projectId}/requirements/${requirementId}/generate`, {
      method: "POST",
    }),

  // --- floor plans ---
  listFloorPlans: (projectId: number) => request<FloorPlan[]>(`/projects/${projectId}/floorplans`),
  latestFloorPlan: (projectId: number) => request<FloorPlan>(`/projects/${projectId}/floorplans/latest`),
  getFloorPlan: (projectId: number, floorPlanId: number) =>
    request<FloorPlan>(`/projects/${projectId}/floorplans/${floorPlanId}`),
  updateFloorPlanStatus: (projectId: number, floorPlanId: number, status: string) =>
    request<FloorPlan>(`/projects/${projectId}/floorplans/${floorPlanId}`, {
      method: "PATCH",
      body: { status },
    }),
  deleteFloorPlan: (projectId: number, floorPlanId: number) =>
    request<void>(`/projects/${projectId}/floorplans/${floorPlanId}`, { method: "DELETE" }),

  // --- shareable links ---
  getShare: (projectId: number, floorPlanId: number) =>
    request<FloorPlanShare | null>(`/projects/${projectId}/floorplans/${floorPlanId}/share`),
  createShare: (projectId: number, floorPlanId: number) =>
    request<FloorPlanShare>(`/projects/${projectId}/floorplans/${floorPlanId}/share`, { method: "POST" }),
  revokeShare: (projectId: number, floorPlanId: number) =>
    request<void>(`/projects/${projectId}/floorplans/${floorPlanId}/share`, { method: "DELETE" }),
  getPublicFloorPlan: (token: string) =>
    request<PublicFloorPlan>(`/public/floorplans/${token}`, { auth: false }),

  // --- furniture editor ---
  updateFurniture: (projectId: number, floorPlanId: number, input: FurnitureLayoutUpdateInput) =>
    request<FloorPlan>(`/projects/${projectId}/floorplans/${floorPlanId}/furniture`, { method: "PUT", body: input }),

  // --- room layout editor ---
  updateRoomLayout: (projectId: number, floorPlanId: number, input: RoomLayoutUpdateInput) =>
    request<FloorPlan>(`/projects/${projectId}/floorplans/${floorPlanId}/rooms`, { method: "PUT", body: input }),
};
