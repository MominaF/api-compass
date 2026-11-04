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
