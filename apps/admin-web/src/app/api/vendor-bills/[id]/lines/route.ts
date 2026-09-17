import { NextRequest, NextResponse } from "next/server";
import { VENDOR_BILL_LINE_FIELDS } from "@/features/vendor-bills/types";
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
    body = await request.json();
  } catch {
    return NextResponse.json(
      { non_field_errors: ["A valid request body is required."] },
      { status: 400 },
    );
  }
  const payload: Record<string, unknown> = {};
  for (const key of VENDOR_BILL_LINE_FIELDS)
    if (body[key] !== undefined) payload[key] = body[key];
  const carrier = NextResponse.json({});
  const result = await authenticatedBackendRequest(
    request.cookies,
    carrier.cookies,
    `finance/vendor-bills/${encodeURIComponent(id)}/lines/`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  const outgoing = result.ok
    ? NextResponse.json(result.data ?? {}, { status: result.status })
    : NextResponse.json(
        backendErrorBody(result, "The Vendor Bill line could not be added."),
        { status: result.status || 503 },
      );
  for (const cookie of carrier.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
