import "server-only";

import { NextRequest, NextResponse } from "next/server";

import { authenticatedBackendRequest } from "@/lib/auth/session";

export async function proxyReferenceList(
  request: NextRequest,
  backendPath: string,
  allowedParams: readonly string[],
  fallbackMessage: string,
) {
  const response = NextResponse.json({}, { status: 200 });
  const query = new URLSearchParams();
  for (const [key, value] of request.nextUrl.searchParams)
    if (allowedParams.includes(key) && value) query.set(key, value);
  const path = `${backendPath}${query.size ? `?${query}` : ""}`;
  const result = await authenticatedBackendRequest<unknown>(
    request.cookies,
    response.cookies,
    path,
  );
  const outgoing =
    result.ok && result.data
      ? NextResponse.json(result.data)
      : NextResponse.json(
          {
            message:
              result.status === 403
                ? "You do not have access to this reference data."
                : result.status === 401
                  ? "Your session has expired."
                  : fallbackMessage,
          },
          { status: result.status || 503 },
        );
  for (const cookie of response.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
