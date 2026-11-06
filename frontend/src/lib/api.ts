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

export type SpecStatus = "processing" | "ready" | "failed";

export type SpecIssue = { message: string; pointer: string | null };

export type SpecSummary = {
  id: string;
  status: SpecStatus;
  validation_errors: SpecIssue[] | null;
  version_number: number;
  source_filename: string;
  format: string;
  openapi_version: string | null;
  api_title: string | null;
  operation_count: number;
  schema_count: number;
  created_at: string;
};

export type SpecMetadata = {
  version: string | null;
  description: string | null;
  servers: { url: string; description?: string }[];
  security_schemes: Record<string, SecurityScheme>;
};

export type SecurityScheme = {
  type: string;
  description?: string;
  scheme?: string;
  bearerFormat?: string;
  name?: string;
  in?: string;
  openIdConnectUrl?: string;
  flows?: Record<string, { authorizationUrl?: string; tokenUrl?: string }>;
};

export type Spec = SpecSummary & { metadata_json: SpecMetadata | null };

export type OperationSummary = {
  id: string;
  operation_id: string | null;
  method: string;
  path: string;
  summary: string | null;
  description: string | null;
  tags: string[];
};

/** The parts below come straight from the uploaded file, so their shape isn't guaranteed. */
export type Operation = OperationSummary & {
  spec_version_id: string;
  parameters_json: unknown[];
  request_body_json: Record<string, unknown> | null;
  responses_json: Record<string, unknown>;
  security_json: unknown[];
};

export type ApiSchema = { id: string; schema_name: string; definition: unknown };

export type OperationFilters = { specId: string; query?: string; methods?: string[] };

export type Project = {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  latest_spec: SpecSummary | null;
};

export type ProjectInput = { name: string; description?: string };

export const listProjects = () => authedFetch<Project[]>("/projects", { cache: "no-store" });

export const getProject = (id: string) =>
  authedFetch<Project>(`/projects/${id}`, { cache: "no-store" });

export const listSpecs = (projectId: string) =>
  authedFetch<Spec[]>(`/projects/${projectId}/specs`, { cache: "no-store" });

export const listOperations = (projectId: string, filters: OperationFilters) => {
  const params = new URLSearchParams({ spec_id: filters.specId });
  if (filters.query) params.set("q", filters.query);
  for (const method of filters.methods ?? []) params.append("method", method);
  return authedFetch<OperationSummary[]>(`/projects/${projectId}/operations?${params}`, {
    cache: "no-store",
  });
};

export const getOperation = (projectId: string, operationId: string) =>
  authedFetch<Operation>(`/projects/${projectId}/operations/${operationId}`, { cache: "no-store" });

export const listSchemas = (projectId: string, specId: string) =>
  authedFetch<ApiSchema[]>(`/projects/${projectId}/schemas?spec_id=${specId}`, {
    cache: "no-store",
  });

/** Resolves even when the import fails: check the returned status and validation_errors. */
export const uploadSpec = (projectId: string, file: File) => {
  const body = new FormData();
  body.append("file", file);
  return authedFetch<Spec>(`/projects/${projectId}/specs`, { method: "POST", body });
};

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
