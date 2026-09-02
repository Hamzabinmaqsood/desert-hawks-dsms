import { NextRequest, NextResponse } from "next/server";

import { isSameOrigin } from "@/lib/auth/origin";
import { refreshSession } from "@/lib/auth/session";

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ authenticated: false }, { status: 403 });
  }
  const response = NextResponse.json({ authenticated: true });
  const refreshed = await refreshSession(request.cookies, response.cookies);
  if (!refreshed) {
    const failed = NextResponse.json({ authenticated: false }, { status: 401 });
    for (const cookie of response.cookies.getAll()) failed.cookies.set(cookie);
    return failed;
  }
  return response;
}
