import { NextRequest, NextResponse } from "next/server";

import { loadSession } from "@/lib/auth/session";

export async function GET(request: NextRequest) {
  const response = NextResponse.json({ authenticated: false }, { status: 401 });
  const result = await loadSession(request.cookies, response.cookies);
  if (result.status === 200 && result.session) {
    const authenticated = NextResponse.json(result.session);
    for (const cookie of response.cookies.getAll())
      authenticated.cookies.set(cookie);
    return authenticated;
  }
  if (result.status === 503) {
    return NextResponse.json(
      {
        authenticated: false,
        message: "Authentication service is unavailable.",
      },
      { status: 503 },
    );
  }
  return response;
}
