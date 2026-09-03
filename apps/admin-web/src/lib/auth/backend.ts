import "server-only";

export interface BackendResult<T> {
  ok: boolean;
  status: number;
  data: T | null;
}

function backendBaseUrl() {
  const value = process.env.BACKEND_API_URL;
  if (!value) throw new Error("BACKEND_API_URL is not configured");
  return value.endsWith("/") ? value : `${value}/`;
}

export async function backendRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<BackendResult<T>> {
  let response: Response;
  try {
    response = await fetch(new URL(path.replace(/^\//, ""), backendBaseUrl()), {
      ...init,
      cache: "no-store",
      headers: { Accept: "application/json", ...init.headers },
    });
  } catch {
    return { ok: false, status: 503, data: null };
  }
  const isJson =
    response.headers.get("content-type")?.includes("application/json") ?? false;
  let data: T | null = null;
  if (isJson) {
    try {
      data = (await response.json()) as T;
    } catch {
      data = null;
    }
  }
  return { ok: response.ok, status: response.status, data };
}

export async function backendDownload(path: string, accessToken: string) {
  try {
    return await fetch(new URL(path.replace(/^\//, ""), backendBaseUrl()), {
      cache: "no-store",
      headers: { Authorization: `Bearer ${accessToken}` },
    });
  } catch {
    return new Response(null, { status: 503 });
  }
}
