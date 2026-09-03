import { NextRequest, NextResponse } from "next/server";

import {
  INVOICE_DRAFT_UPDATE_FIELDS,
  type InvoiceDetail,
} from "@/features/invoices/types";
import { backendErrorBody } from "@/lib/api/backend-error";
import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest } from "@/lib/auth/session";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const response = NextResponse.json({}, { status: 200 });
  const result = await authenticatedBackendRequest<InvoiceDetail>(
    request.cookies,
    response.cookies,
    `billing/invoices/${encodeURIComponent(id)}/`,
  );
  const outgoing =
    result.ok && result.data
      ? NextResponse.json(result.data)
      : NextResponse.json(
          {
            message:
              result.status === 404
                ? "Invoice not found."
                : result.status === 403
                  ? "You do not have access to invoices."
                  : result.status === 401
                    ? "Your session has expired."
                    : "The invoice could not be loaded.",
          },
          { status: result.status || 503 },
        );
  for (const cookie of response.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}

export async function PATCH(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  if (!isSameOrigin(request))
    return NextResponse.json(
      { non_field_errors: ["Request origin is not allowed."] },
      { status: 403 },
    );
  const { id } = await context.params;
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
  for (const key of INVOICE_DRAFT_UPDATE_FIELDS)
    if (body[key] !== undefined) payload[key] = body[key];

  const response = NextResponse.json({}, { status: 200 });
  const result = await authenticatedBackendRequest<InvoiceDetail>(
    request.cookies,
    response.cookies,
    `billing/invoices/${encodeURIComponent(id)}/`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  const outgoing =
    result.ok && result.data
      ? NextResponse.json(result.data)
      : NextResponse.json(
          backendErrorBody(result, "The invoice could not be updated."),
          { status: result.status || 503 },
        );
  for (const cookie of response.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
