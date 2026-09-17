import { NextRequest, NextResponse } from "next/server";
import { VENDOR_BILL_LINE_FIELDS } from "@/features/vendor-bills/types";
import { backendErrorBody } from "@/lib/api/backend-error";
import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest } from "@/lib/auth/session";
type Context = { params: Promise<{ id: string; lineId: string }> };
const path = (id: string, lineId: string) =>
  `finance/vendor-bills/${encodeURIComponent(id)}/lines/${encodeURIComponent(lineId)}/`;
export async function PATCH(request: NextRequest, context: Context) {
  if (!isSameOrigin(request))
    return NextResponse.json(
      { non_field_errors: ["Request origin is not allowed."] },
      { status: 403 },
    );
  const { id, lineId } = await context.params;
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
    path(id, lineId),
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  const outgoing = result.ok
    ? NextResponse.json(result.data ?? {})
    : NextResponse.json(
        backendErrorBody(result, "The Vendor Bill line could not be updated."),
        { status: result.status || 503 },
      );
  for (const cookie of carrier.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
export async function DELETE(request: NextRequest, context: Context) {
  if (!isSameOrigin(request))
    return NextResponse.json(
      { non_field_errors: ["Request origin is not allowed."] },
      { status: 403 },
    );
  const { id, lineId } = await context.params;
  const carrier = NextResponse.json({});
  const result = await authenticatedBackendRequest(
    request.cookies,
    carrier.cookies,
    path(id, lineId),
    { method: "DELETE" },
  );
  const outgoing =
    result.ok || result.status === 204
      ? NextResponse.json({ ok: true })
      : NextResponse.json(
          backendErrorBody(
            result,
            "The Vendor Bill line could not be removed.",
          ),
          { status: result.status || 503 },
        );
  for (const cookie of carrier.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
