import { NextRequest, NextResponse } from "next/server";

import { INVOICE_LINE_WRITE_FIELDS } from "@/features/invoices/types";
import { backendErrorBody } from "@/lib/api/backend-error";
import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest } from "@/lib/auth/session";

export async function POST(
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
  for (const key of INVOICE_LINE_WRITE_FIELDS)
    if (body[key] !== undefined) payload[key] = body[key];

  const response = NextResponse.json({}, { status: 200 });
  const result = await authenticatedBackendRequest<unknown>(
    request.cookies,
    response.cookies,
    `billing/invoices/${encodeURIComponent(id)}/lines/`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  const outgoing = result.ok
    ? NextResponse.json(result.data ?? {}, { status: result.status })
    : NextResponse.json(
        backendErrorBody(result, "The invoice line could not be added."),
        { status: result.status || 503 },
      );
  for (const cookie of response.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
