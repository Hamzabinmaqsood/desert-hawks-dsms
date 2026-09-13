import { NextRequest, NextResponse } from "next/server";

import {
  RECEIPT_CREATE_FIELDS,
  type ReceiptPage,
  type Receipt,
} from "@/features/receipts/types";
import { backendErrorBody } from "@/lib/api/backend-error";
import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest } from "@/lib/auth/session";

const filters = new Set([
  "company",
  "client",
  "status",
  "payment_method",
  "search",
  "ordering",
  "page",
]);

function copyCookies(source: NextResponse, target: NextResponse) {
  for (const cookie of source.cookies.getAll()) target.cookies.set(cookie);
  return target;
}

export async function GET(request: NextRequest) {
  const response = NextResponse.json({});
  const query = new URLSearchParams();
  for (const [key, value] of request.nextUrl.searchParams)
    if (filters.has(key) && value) query.set(key, value);
  const result = await authenticatedBackendRequest<ReceiptPage>(
    request.cookies,
    response.cookies,
    `billing/receipts/${query.size ? `?${query}` : ""}`,
  );
  return copyCookies(
    response,
    result.ok && result.data
      ? NextResponse.json(result.data)
      : NextResponse.json(
          backendErrorBody(result, "Receipts could not be loaded."),
          { status: result.status || 503 },
        ),
  );
}

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request))
    return NextResponse.json(
      { non_field_errors: ["Request origin is not allowed."] },
      { status: 403 },
    );
  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json(
      { non_field_errors: ["A valid request body is required."] },
      { status: 400 },
    );
  }
  const payload: Record<string, unknown> = {};
  for (const key of RECEIPT_CREATE_FIELDS)
    if (body[key] !== undefined) payload[key] = body[key];
  const response = NextResponse.json({});
  const result = await authenticatedBackendRequest<Receipt>(
    request.cookies,
    response.cookies,
    "billing/receipts/",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return copyCookies(
    response,
    result.ok && result.data
      ? NextResponse.json(result.data, { status: result.status })
      : NextResponse.json(
          backendErrorBody(result, "The receipt could not be created."),
          { status: result.status || 503 },
        ),
  );
}
