import { NextRequest, NextResponse } from "next/server";

import { backendRequest } from "@/lib/auth/backend";
import {
  clearCompanyContextCookie,
  setSessionCookies,
} from "@/lib/auth/cookies";
import { isSameOrigin } from "@/lib/auth/origin";

interface TokenPair {
  access: string;
  refresh: string;
}

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return NextResponse.json(
      { message: "Request origin is not allowed." },
      { status: 403 },
    );
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { message: "Email and password are required." },
      { status: 400 },
    );
  }
  const email =
    typeof (body as { email?: unknown })?.email === "string"
      ? (body as { email: string }).email.trim()
      : "";
  const password =
    typeof (body as { password?: unknown })?.password === "string"
      ? (body as { password: string }).password
      : "";
  if (!email || !password) {
    return NextResponse.json(
      { message: "Enter your email and password.", fieldErrors: {} },
      { status: 400 },
    );
  }
  const result = await backendRequest<TokenPair>("auth/login/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!result.ok || !result.data?.access || !result.data.refresh) {
    const status = result.status === 401 ? 401 : 503;
    const message =
      status === 401
        ? "Email or password is incorrect."
        : "Authentication service is unavailable.";
    return NextResponse.json({ message, fieldErrors: {} }, { status });
  }
  const response = NextResponse.json({ authenticated: true });
  clearCompanyContextCookie(response.cookies);
  setSessionCookies(response.cookies, result.data);
  return response;
}
