/**
 * Typed API Client for Bookinistic Studio 2.0 Backend.
 *
 * Implements ADR-1 (FastAPI endpoints), ADR-10 (Zero-Trust Session Token Guard)
 * and cancellation via AbortController.
 */

let sessionToken: string | null = null;

export function setSessionToken(token: string | null): void {
  sessionToken = token;
}

export function getSessionToken(): string | null {
  return sessionToken;
}

export interface RequestOptions extends RequestInit {
  timeoutMs?: number;
}

export class ApiError extends Error {
  public status: number;
  public details: unknown;

  constructor(message: string, status: number, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

export async function apiRequest<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const { timeoutMs = 30000, headers = {}, signal, ...rest } = options;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  // Link caller signal with timeout controller if provided
  if (signal) {
    signal.addEventListener("abort", () => controller.abort());
  }

  const mergedHeaders: Record<string, string> = {
    Accept: "application/json",
    ...(headers as Record<string, string>),
  };

  if (sessionToken) {
    mergedHeaders["X-Mobile-Token"] = sessionToken;
  }

  // Auto-detect JSON payload
  if (rest.body && typeof rest.body === "string" && !mergedHeaders["Content-Type"]) {
    mergedHeaders["Content-Type"] = "application/json";
  }

  const url = endpoint.startsWith("http") ? endpoint : endpoint.startsWith("/") ? endpoint : `/${endpoint}`;

  try {
    const response = await fetch(url, {
      ...rest,
      headers: mergedHeaders,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      let errorDetail: unknown = null;
      try {
        errorDetail = await response.json();
      } catch {
        errorDetail = await response.text();
      }
      const msg =
        typeof errorDetail === "object" && errorDetail !== null && "detail" in errorDetail
          ? String((errorDetail as { detail: unknown }).detail)
          : `HTTP ${response.status}: ${response.statusText}`;
      throw new ApiError(msg, response.status, errorDetail);
    }

    if (response.status === 204) {
      return {} as T;
    }

    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return (await response.json()) as T;
    }
    return (await response.text()) as unknown as T;
  } catch (err: unknown) {
    clearTimeout(timeoutId);
    if (err instanceof ApiError) {
      throw err;
    }
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("Request aborted or timed out", 408);
    }
    throw new ApiError(err instanceof Error ? err.message : String(err), 500);
  }
}

