import { NextRequest, NextResponse } from "next/server";

import { backendRequest } from "@/lib/auth/backend";
import {
  ACCESS_COOKIE,
  clearSessionCookies,
  REFRESH_COOKIE,
} from "@/lib/auth/cookies";
import { isSameOrigin } from "@/lib/auth/origin";
import { refreshSession } from "@/lib/auth/session";

export async function POST(request: NextRequest) {
  const response = NextResponse.json({ authenticated: false });
  if (!isSameOrigin(request)) {
    clearSessionCookies(response.cookies);
    return NextResponse.json(
      { authenticated: false },
      { status: 403, headers: response.headers },
    );
  }
  let access = request.cookies.get(ACCESS_COOKIE)?.value;
  let refresh = request.cookies.get(REFRESH_COOKIE)?.value;
  let backendSucceeded = true;
  if (access && refresh) {
    const revoke = () =>
      backendRequest<never>("auth/logout/", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${access}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ refresh }),
      });
    let result = await revoke();
    if (
      result.status === 401 &&
      (await refreshSession(request.cookies, response.cookies))
    ) {
      access = response.cookies.get(ACCESS_COOKIE)?.value;
      refresh = response.cookies.get(REFRESH_COOKIE)?.value;
      if (access && refresh) result = await revoke();
    }
    backendSucceeded = result.ok;
  }
  clearSessionCookies(response.cookies);
  if (!backendSucceeded)
    response.headers.set("X-Session-Revocation", "backend-unavailable");
  return response;
}
