import { NextRequest, NextResponse } from "next/server";

import { backendErrorBody } from "@/lib/api/backend-error";
import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest } from "@/lib/auth/session";

const UUID = "[0-9a-fA-F-]{36}";
const ALLOWED = new Map<string, RegExp[]>([
  [
    "GET",
    [
      /^modules\/$/,
      /^plans\/$/,
      new RegExp(`^plans/${UUID}/entitlements/$`),
      /^subscriptions\/$/,
      new RegExp(`^subscriptions/${UUID}/entitlements/$`),
      /^tenants\/$/,
    ],
  ],
  [
    "POST",
    [
      /^plans\/$/,
      /^subscriptions\/$/,
      /^provisioning\/$/,
      new RegExp(`^subscriptions/${UUID}/apply-plan-revision/$`),
      new RegExp(`^subscriptions/${UUID}/activate-entitlements/$`),
    ],
  ],
  [
    "PUT",
    [
      new RegExp(`^plans/${UUID}/entitlements/$`),
      new RegExp(`^subscriptions/${UUID}/overrides/$`),
    ],
  ],
]);

function copyCookies(source: NextResponse, target: NextResponse) {
  for (const cookie of source.cookies.getAll()) target.cookies.set(cookie);
  return target;
}

export async function proxyPlatformRequest(
  request: NextRequest,
  method: "GET" | "POST" | "PUT",
  segments: string[],
) {
  const path = `${segments.join("/")}/`;
  if (!ALLOWED.get(method)?.some((pattern) => pattern.test(path)))
    return NextResponse.json(
      { message: "Platform route not found." },
      { status: 404 },
    );
  if (method !== "GET" && !isSameOrigin(request))
    return NextResponse.json(
      { non_field_errors: ["Request origin is not allowed."] },
      { status: 403 },
    );

  let body: string | undefined;
  if (method !== "GET") {
    try {
      body = JSON.stringify(await request.json());
    } catch {
      return NextResponse.json(
        { non_field_errors: ["A valid request body is required."] },
        { status: 400 },
      );
    }
  }
  const carrier = NextResponse.json({});
  const result = await authenticatedBackendRequest<unknown>(
    request.cookies,
    carrier.cookies,
    `platform/${path}`,
    {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body,
    },
  );
  const outgoing =
    result.ok && result.data !== null
      ? NextResponse.json(result.data, { status: result.status })
      : NextResponse.json(
          backendErrorBody(
            result,
            "The platform request could not be completed.",
          ),
          { status: result.status || 503 },
        );
  return copyCookies(carrier, outgoing);
}
