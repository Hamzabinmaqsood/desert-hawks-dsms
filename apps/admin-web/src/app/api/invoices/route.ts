import { NextRequest, NextResponse } from "next/server";

import { authenticatedBackendRequest } from "@/lib/auth/session";
import { isSameOrigin } from "@/lib/auth/origin";
import { backendErrorBody } from "@/lib/api/backend-error";
import {
  INVOICE_CREATE_FIELDS,
  type InvoiceDetail,
  type PaginatedResponse,
} from "@/features/invoices/types";

const allowed = new Set([
  "company",
  "client",
  "contract",
  "status",
  "invoice_type",
  "search",
  "ordering",
  "page",
]);

export async function GET(request: NextRequest) {
  const response = NextResponse.json({}, { status: 200 });
  const query = new URLSearchParams();
  for (const [key, value] of request.nextUrl.searchParams)
    if (allowed.has(key) && value) query.set(key, value);
  const path = `billing/invoices/${query.size ? `?${query}` : ""}`;
  const result = await authenticatedBackendRequest<
    PaginatedResponse<InvoiceDetail>
  >(request.cookies, response.cookies, path);
  const outgoing =
    result.ok && result.data
      ? NextResponse.json(result.data)
      : NextResponse.json(
          {
            message:
              result.status === 403
                ? "You do not have access to invoices."
                : result.status === 401
                  ? "Your session has expired."
                  : "Invoices could not be loaded.",
          },
          { status: result.status || 503 },
        );
  for (const cookie of response.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
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
  for (const key of INVOICE_CREATE_FIELDS)
    if (body[key] !== undefined) payload[key] = body[key];

  const response = NextResponse.json({}, { status: 200 });
  const result = await authenticatedBackendRequest<InvoiceDetail>(
    request.cookies,
    response.cookies,
    "billing/invoices/",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  const outgoing =
    result.ok && result.data
      ? NextResponse.json(result.data, { status: result.status })
      : NextResponse.json(
          backendErrorBody(result, "The invoice could not be created."),
          { status: result.status || 503 },
        );
  for (const cookie of response.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
