import "server-only";

import type { ResponseCookies } from "next/dist/compiled/@edge-runtime/cookies";

export const ACCESS_COOKIE = "dh_access";
export const REFRESH_COOKIE = "dh_refresh";
export const ACCESS_MAX_AGE = 15 * 60;
export const REFRESH_MAX_AGE = 7 * 24 * 60 * 60;

const secure = process.env.NODE_ENV === "production";

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
  for (const name of [ACCESS_COOKIE, REFRESH_COOKIE]) {
    cookies.set(name, "", {
      httpOnly: true,
      secure,
      sameSite: "lax",
      path: "/",
      maxAge: 0,
    });
  }
}
