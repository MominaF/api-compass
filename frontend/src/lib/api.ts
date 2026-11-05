import { getSupabase } from "@/lib/supabase";

/**
 * Typed client for the FastAPI backend. All backend errors share one envelope:
 *   { "error": { "code": string, "message": string, "details"?: unknown } }
 */

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly body?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type ErrorEnvelope = { error: { code: string; message: string; details?: unknown } };

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as ErrorEnvelope).error?.message === "string"
  );
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit & { acceptStatuses?: number[] },
): Promise<T> {
  const { acceptStatuses = [], ...requestInit } = init ?? {};
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/v1${path}`, {
      ...requestInit,
      headers: { Accept: "application/json", ...requestInit.headers },
    });
  } catch {
    throw new ApiError(0, "network_error", `Cannot reach the API at ${API_BASE_URL}.`);
  }

  const body: unknown = await res.json().catch(() => undefined);
  if (res.ok || acceptStatuses.includes(res.status)) return body as T;

  if (isErrorEnvelope(body)) {
    throw new ApiError(res.status, body.error.code, body.error.message, body);
  }
  throw new ApiError(res.status, "http_error", `Request failed with status ${res.status}.`, body);
}

/** Like apiFetch, but sends the user's access token. A rejected token ends the local session. */
async function authedFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const supabase = getSupabase();
  const { data } = (await supabase?.auth.getSession()) ?? { data: { session: null } };
  if (!data.session) throw new ApiError(401, "unauthorized", "Sign in to continue.");
  try {
    return await apiFetch<T>(path, {
      ...init,
      headers: { ...init?.headers, Authorization: `Bearer ${data.session.access_token}` },
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      await supabase?.auth.signOut({ scope: "local" });
    }
    throw error;
  }
}

export type Project = {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type ProjectInput = { name: string; description?: string };

export const listProjects = () => authedFetch<Project[]>("/projects", { cache: "no-store" });

export const createProject = (input: ProjectInput) =>
  authedFetch<Project>("/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });

export const deleteProject = (id: string) =>
  authedFetch<void>(`/projects/${id}`, { method: "DELETE" });

export type HealthResponse = {
  status: "ok" | "degraded";
  service: string;
  version: string;
  environment: string;
  database: "ok" | "unavailable";
};

export const getHealth = () =>
  // 503 still carries a valid health body (database unavailable), so accept it.
  apiFetch<HealthResponse>("/health", { cache: "no-store", acceptStatuses: [503] });
