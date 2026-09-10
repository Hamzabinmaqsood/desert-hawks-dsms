import { NextRequest, NextResponse } from "next/server";

import { ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/auth/cookies";
import { loadSession } from "@/lib/auth/session";

function copyCookies(from: NextResponse, to: NextResponse) {
  for (const cookie of from.cookies.getAll()) to.cookies.set(cookie);
}

export async function proxy(request: NextRequest) {
  if (request.nextUrl.pathname.startsWith("/brand/"))
    return NextResponse.next();
  const isLogin = request.nextUrl.pathname === "/login";
  const hasSession =
    request.cookies.has(ACCESS_COOKIE) && request.cookies.has(REFRESH_COOKIE);
  if (isLogin && !hasSession) return NextResponse.next();

  const cookieResponse = NextResponse.next();
  const session = await loadSession(request.cookies, cookieResponse.cookies);
  if (session.status === 200 && session.session) {
    if (isLogin) {
      const redirect = NextResponse.redirect(
        new URL("/dashboard", request.url),
      );
      copyCookies(cookieResponse, redirect);
      return redirect;
    }
    const rotatedAccess = cookieResponse.cookies.get(ACCESS_COOKIE);
    const rotatedRefresh = cookieResponse.cookies.get(REFRESH_COOKIE);
    if (rotatedAccess)
      request.cookies.set(rotatedAccess.name, rotatedAccess.value);
    if (rotatedRefresh)
      request.cookies.set(rotatedRefresh.name, rotatedRefresh.value);
    const next = NextResponse.next({ request: { headers: request.headers } });
    copyCookies(cookieResponse, next);
    return next;
  }
  if (isLogin) return NextResponse.next();
  const redirect = NextResponse.redirect(new URL("/login", request.url));
  copyCookies(cookieResponse, redirect);
  return redirect;
}

export const config = {
  matcher: [
    "/login",
    "/((?!api|brand|_next/static|_next/image|favicon.ico).*)",
  ],
};
