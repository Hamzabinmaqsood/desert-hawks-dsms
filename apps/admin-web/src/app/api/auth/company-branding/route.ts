import { NextRequest, NextResponse } from "next/server";

import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest } from "@/lib/auth/session";
import type { CompanyBranding } from "@/lib/auth/types";
import { isBrandColor, normalizeBrandColor } from "@/lib/branding";

const supportedFields = new Set([
  "display_name",
  "tagline",
  "primary_color",
  "accent_color",
]);

function copyCookies(source: NextResponse, target: NextResponse) {
  for (const cookie of source.cookies.getAll()) target.cookies.set(cookie);
  return target;
}

function normalizedResponse(
  result: Awaited<
    ReturnType<typeof authenticatedBackendRequest<CompanyBranding>>
  >,
  cookieResponse: NextResponse,
) {
  if (result.ok && result.data)
    return copyCookies(cookieResponse, NextResponse.json(result.data));
  const status =
    result.status === 400 || result.status === 403 || result.status === 404
      ? result.status
      : result.status === 401
        ? 401
        : 503;
  const message =
    status === 400
      ? "Review the branding fields and try again."
      : status === 403
        ? "You do not have permission to manage this Company branding."
        : status === 404
          ? "No active Company branding is available."
          : status === 401
            ? "Your session has expired."
            : "Company branding is temporarily unavailable.";
  return copyCookies(
    cookieResponse,
    NextResponse.json(
      {
        message,
        fieldErrors:
          status === 400 && result.data && typeof result.data === "object"
            ? result.data
            : {},
      },
      { status },
    ),
  );
}

export async function GET(request: NextRequest) {
  const cookieResponse = NextResponse.json({}, { status: 200 });
  const result = await authenticatedBackendRequest<CompanyBranding>(
    request.cookies,
    cookieResponse.cookies,
    "auth/company-branding/",
  );
  return normalizedResponse(result, cookieResponse);
}

export async function PATCH(request: NextRequest) {
  if (!isSameOrigin(request))
    return NextResponse.json(
      { message: "Request origin is not allowed.", fieldErrors: {} },
      { status: 403 },
    );
  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json(
      { message: "Submit valid branding data.", fieldErrors: {} },
      { status: 400 },
    );
  }
  const unsupported = Object.keys(body).filter(
    (key) => !supportedFields.has(key),
  );
  if (unsupported.length)
    return NextResponse.json(
      {
        message: "Unsupported branding fields were supplied.",
        fieldErrors: Object.fromEntries(
          unsupported.map((field) => [field, ["This field is not supported."]]),
        ),
      },
      { status: 400 },
    );
  const payload: Record<string, string> = {};
  for (const [field, value] of Object.entries(body)) {
    if (typeof value !== "string")
      return NextResponse.json(
        {
          message: "Review the branding fields and try again.",
          fieldErrors: { [field]: ["Enter a text value."] },
        },
        { status: 400 },
      );
    payload[field] = value.trim();
  }
  for (const field of ["primary_color", "accent_color"]) {
    const value = payload[field];
    if (value !== undefined) {
      if (value && !isBrandColor(value))
        return NextResponse.json(
          {
            message: "Review the branding fields and try again.",
            fieldErrors: { [field]: ["Enter a color in #RRGGBB format."] },
          },
          { status: 400 },
        );
      payload[field] = value ? normalizeBrandColor(value) : "";
    }
  }
  const cookieResponse = NextResponse.json({}, { status: 200 });
  const result = await authenticatedBackendRequest<CompanyBranding>(
    request.cookies,
    cookieResponse.cookies,
    "auth/company-branding/",
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return normalizedResponse(result, cookieResponse);
}
