import { NextRequest, NextResponse } from "next/server";

import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest } from "@/lib/auth/session";
import type { CompanyBusinessSettings } from "@/lib/auth/types";

const supportedFields = new Set([
  "default_currency",
  "timezone",
  "invoice_number_prefix",
  "receipt_number_prefix",
  "credit_note_number_prefix",
  "debit_note_number_prefix",
]);
const prefixPattern = /^[A-Z0-9](?:[A-Z0-9_-]{0,8}[A-Z0-9])?$/;

function copyCookies(source: NextResponse, target: NextResponse) {
  for (const cookie of source.cookies.getAll()) target.cookies.set(cookie);
  return target;
}

function normalizedResponse(
  result: Awaited<
    ReturnType<typeof authenticatedBackendRequest<CompanyBusinessSettings>>
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
      ? "Review the business settings and try again."
      : status === 403
        ? "You do not have permission to manage these Company settings."
        : status === 404
          ? "No active Company settings are available."
          : status === 401
            ? "Your session has expired."
            : "Company business settings are temporarily unavailable.";
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
  const result = await authenticatedBackendRequest<CompanyBusinessSettings>(
    request.cookies,
    cookieResponse.cookies,
    "auth/company-business-settings/",
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
      { message: "Submit valid business settings.", fieldErrors: {} },
      { status: 400 },
    );
  }
  const unsupported = Object.keys(body).filter(
    (key) => !supportedFields.has(key),
  );
  if (unsupported.length)
    return NextResponse.json(
      {
        message: "Unsupported business-setting fields were supplied.",
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
          message: "Review the business settings and try again.",
          fieldErrors: { [field]: ["Enter a text value."] },
        },
        { status: 400 },
      );
    payload[field] = value.trim();
  }
  if (
    payload.default_currency !== undefined &&
    !/^[A-Za-z]{3}$/.test(payload.default_currency)
  )
    return NextResponse.json(
      {
        message: "Review the business settings and try again.",
        fieldErrors: {
          default_currency: ["Enter a three-letter currency code."],
        },
      },
      { status: 400 },
    );
  if (payload.default_currency)
    payload.default_currency = payload.default_currency.toUpperCase();
  for (const field of [
    "invoice_number_prefix",
    "receipt_number_prefix",
    "credit_note_number_prefix",
    "debit_note_number_prefix",
  ]) {
    const value = payload[field];
    if (value !== undefined) {
      payload[field] = value.toUpperCase();
      if (!prefixPattern.test(payload[field]))
        return NextResponse.json(
          {
            message: "Review the business settings and try again.",
            fieldErrors: { [field]: ["Enter a valid 1-10 character prefix."] },
          },
          { status: 400 },
        );
    }
  }
  const cookieResponse = NextResponse.json({}, { status: 200 });
  const result = await authenticatedBackendRequest<CompanyBusinessSettings>(
    request.cookies,
    cookieResponse.cookies,
    "auth/company-business-settings/",
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return normalizedResponse(result, cookieResponse);
}
