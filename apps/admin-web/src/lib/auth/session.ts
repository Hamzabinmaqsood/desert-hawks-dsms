import "server-only";

import type { ReadonlyRequestCookies } from "next/dist/server/web/spec-extension/adapters/request-cookies";
import type { ResponseCookies } from "next/dist/compiled/@edge-runtime/cookies";

import {
  backendDownload,
  backendRequest,
  type BackendResult,
} from "@/lib/auth/backend";
import {
  ACCESS_COOKIE,
  clearSessionCookies,
  REFRESH_COOKIE,
  setSessionCookies,
} from "@/lib/auth/cookies";
import type { AccessScopes, CurrentUser, SessionData } from "@/lib/auth/types";

interface TokenPair {
  access: string;
  refresh?: string;
}

type CookieReader = Pick<ReadonlyRequestCookies, "get">;
const refreshes = new Map<string, Promise<TokenPair | null>>();

async function refreshTokens(refresh: string): Promise<TokenPair | null> {
  const running = refreshes.get(refresh);
  if (running) return running;
  const promise = (async () => {
    const result = await backendRequest<TokenPair>("auth/refresh/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });
    return result.ok && result.data?.access ? result.data : null;
  })();
  refreshes.set(refresh, promise);
  try {
    return await promise;
  } finally {
    refreshes.delete(refresh);
  }
}

async function fetchIdentity(access: string) {
  const headers = { Authorization: `Bearer ${access}` };
  const [user, permissions, scopes] = await Promise.all([
    backendRequest<CurrentUser>("auth/me/", { headers }),
    backendRequest<{ permissions: string[] }>("auth/me/permissions/", {
      headers,
    }),
    backendRequest<AccessScopes>("auth/me/access-scopes/", { headers }),
  ]);
  if ([user, permissions, scopes].some((result) => result.status === 401))
    return { status: 401 };
  if (
    !user.ok ||
    !permissions.ok ||
    !scopes.ok ||
    !user.data ||
    !permissions.data ||
    !scopes.data
  ) {
    return { status: 503 };
  }
  return {
    status: 200,
    session: {
      authenticated: true,
      user: user.data,
      permissions: permissions.data.permissions,
      scopes: scopes.data,
    } satisfies SessionData,
  };
}

export async function loadSession(
  reader: CookieReader,
  writer?: ResponseCookies,
) {
  const access = reader.get(ACCESS_COOKIE)?.value;
  const refresh = reader.get(REFRESH_COOKIE)?.value;
  if (!access || !refresh) return { status: 401 as const };

  const first = await fetchIdentity(access);
  if (first.status !== 401) return first;

  const tokens = await refreshTokens(refresh);
  if (!tokens) {
    if (writer) clearSessionCookies(writer);
    return { status: 401 as const };
  }
  if (writer)
    setSessionCookies(writer, {
      access: tokens.access,
      refresh: tokens.refresh ?? refresh,
    });
  const retried = await fetchIdentity(tokens.access);
  if (retried.status === 401 && writer) clearSessionCookies(writer);
  return retried;
}

export async function refreshSession(
  reader: CookieReader,
  writer: ResponseCookies,
) {
  const refresh = reader.get(REFRESH_COOKIE)?.value;
  if (!refresh) {
    clearSessionCookies(writer);
    return false;
  }
  const tokens = await refreshTokens(refresh);
  if (!tokens) {
    clearSessionCookies(writer);
    return false;
  }
  setSessionCookies(writer, {
    access: tokens.access,
    refresh: tokens.refresh ?? refresh,
  });
  return true;
}

export async function authenticatedBackendRequest<T>(
  reader: CookieReader,
  writer: ResponseCookies,
  path: string,
  init: RequestInit = {},
): Promise<BackendResult<T>> {
  const access = reader.get(ACCESS_COOKIE)?.value;
  const refresh = reader.get(REFRESH_COOKIE)?.value;
  if (!access || !refresh) return { ok: false, status: 401, data: null };
  const send = (token: string) =>
    backendRequest<T>(path, {
      ...init,
      headers: { ...init.headers, Authorization: `Bearer ${token}` },
    });
  const first = await send(access);
  if (first.status !== 401) return first;
  const tokens = await refreshTokens(refresh);
  if (!tokens) {
    clearSessionCookies(writer);
    return { ok: false, status: 401, data: null };
  }
  setSessionCookies(writer, {
    access: tokens.access,
    refresh: tokens.refresh ?? refresh,
  });
  const retried = await send(tokens.access);
  if (retried.status === 401) clearSessionCookies(writer);
  return retried;
}

export async function authenticatedBackendDownload(
  reader: CookieReader,
  writer: ResponseCookies,
  path: string,
) {
  const access = reader.get(ACCESS_COOKIE)?.value;
  const refresh = reader.get(REFRESH_COOKIE)?.value;
  if (!access || !refresh) return null;
  let result = await backendDownload(path, access);
  if (result.status !== 401) return result;
  const tokens = await refreshTokens(refresh);
  if (!tokens) {
    clearSessionCookies(writer);
    return null;
  }
  setSessionCookies(writer, {
    access: tokens.access,
    refresh: tokens.refresh ?? refresh,
  });
  result = await backendDownload(path, tokens.access);
  if (result.status === 401) clearSessionCookies(writer);
  return result;
}
