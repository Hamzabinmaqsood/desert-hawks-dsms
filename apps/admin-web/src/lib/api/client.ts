const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;

export class ApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly details?: unknown) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!API_BASE_URL) {
    throw new ApiError(0, "NEXT_PUBLIC_API_BASE_URL is not configured");
  }
  let response: Response;
  try {
    response = await fetch(new URL(path, `${API_BASE_URL}/`), {
      ...init,
      headers: { Accept: "application/json", ...init.headers },
    });
  } catch (error) {
    throw new ApiError(0, "Network request failed", error);
  }
  const isJson = response.headers.get("content-type")?.includes("application/json") ?? false;
  const body: unknown = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    throw new ApiError(response.status, `API request failed with status ${response.status}`, body);
  }
  return body as T;
}
