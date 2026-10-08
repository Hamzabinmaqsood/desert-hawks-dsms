import "server-only";

import type { ResponseCookies } from "next/dist/compiled/@edge-runtime/cookies";

export const ACCESS_COOKIE = "dh_access";
export const REFRESH_COOKIE = "dh_refresh";
export const COMPANY_CONTEXT_COOKIE = "dh_company_context";
export const ACCESS_MAX_AGE = 15 * 60;
export const REFRESH_MAX_AGE = 7 * 24 * 60 * 60;

const secure = process.env.NODE_ENV === "production";

type CookieReader = {
  get(name: string): { value: string } | undefined;
};

export function backendSessionHeaders(
  reader: CookieReader,
): Record<string, string> {
  const value = reader.get(COMPANY_CONTEXT_COOKIE)?.value;
  return value && /^[a-zA-Z0-9]+$/.test(value)
    ? { Cookie: `sessionid=${value}` }
    : {};
}

export function syncCompanyContextCookie(
  cookies: ResponseCookies,
  headers?: Headers,
) {
  const setCookie = headers?.get("set-cookie");
  const match = setCookie?.match(/(?:^|,\s*)sessionid=([^;]*)/i);
  if (!match) return;
  const value = match[1];
  if (!value) {
    clearCompanyContextCookie(cookies);
    return;
  }
  cookies.set(COMPANY_CONTEXT_COOKIE, value, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: REFRESH_MAX_AGE,
  });
}

export function clearCompanyContextCookie(cookies: ResponseCookies) {
  cookies.set(COMPANY_CONTEXT_COOKIE, "", {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
}

export function setSessionCookies(
  cookies: ResponseCookies,
  tokens: { access: string; refresh?: string },
) {
  cookies.set(ACCESS_COOKIE, tokens.access, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: ACCESS_MAX_AGE,
  });
  if (tokens.refresh) {
    cookies.set(REFRESH_COOKIE, tokens.refresh, {
      httpOnly: true,
      secure,
      sameSite: "lax",
      path: "/",
      maxAge: REFRESH_MAX_AGE,
    });
  }
}

export function clearSessionCookies(cookies: ResponseCookies) {
  for (const name of [ACCESS_COOKIE, REFRESH_COOKIE, COMPANY_CONTEXT_COOKIE]) {
    cookies.set(name, "", {
      httpOnly: true,
      secure,
      sameSite: "lax",
      path: "/",
      maxAge: 0,
    });
  }
}
