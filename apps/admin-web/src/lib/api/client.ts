export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly fieldErrors: Record<string, string[]> = {},
    public readonly nonFieldErrors: string[] = [],
    public readonly code = "",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type ApiResponseType = "json" | "blob" | "response";

export interface ApiFetchOptions extends RequestInit {
  query?: Record<string, string | number | boolean | null | undefined>;
  responseType?: ApiResponseType;
}

function normalizedError(status: number, body: unknown): ApiError {
  const fieldErrors: Record<string, string[]> = {};
  const nonFieldErrors: string[] = [];
  let code = "";
  if (body && typeof body === "object" && !Array.isArray(body)) {
    for (const [key, value] of Object.entries(body)) {
      const messages = (Array.isArray(value) ? value : [value]).filter(
        (item): item is string => typeof item === "string",
      );
      if (key === "code") code = messages[0] ?? "";
      else if (
        key === "detail" ||
        key === "message" ||
        key === "non_field_errors"
      )
        nonFieldErrors.push(...messages);
      else if (messages.length) fieldErrors[key] = messages;
    }
  }
  const message =
    nonFieldErrors[0] ??
    (status === 401
      ? "Your session is not authenticated."
      : "The request could not be completed.");
  return new ApiError(status, message, fieldErrors, nonFieldErrors, code);
}

export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { query, responseType = "json", ...init } = options;
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== null && value !== undefined)
      url.searchParams.set(key, String(value));
  }
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      credentials: "same-origin",
      headers: { Accept: "application/json", ...init.headers },
    });
  } catch (error) {
    throw new ApiError(0, "The server could not be reached.", {}, [
      String(error),
    ]);
  }
  if (responseType === "response" && response.ok) return response as T;
  if (responseType === "blob" && response.ok)
    return (await response.blob()) as T;
  const isJson =
    response.headers.get("content-type")?.includes("application/json") ?? false;
  const body: unknown = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    const error = normalizedError(response.status, body);
    if (error.code === "module_not_enabled")
      window.dispatchEvent(new Event("dsms:module-not-enabled"));
    throw error;
  }
  return body as T;
}
