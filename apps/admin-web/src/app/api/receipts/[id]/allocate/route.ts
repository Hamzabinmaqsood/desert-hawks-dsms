import { NextRequest, NextResponse } from "next/server";
import { RECEIPT_ALLOCATION_FIELDS } from "@/features/receipts/types";
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
  for (const key of RECEIPT_ALLOCATION_FIELDS)
    if (body[key] !== undefined) payload[key] = body[key];
  const response = NextResponse.json({});
  const result = await authenticatedBackendRequest(
    request.cookies,
    response.cookies,
    `billing/receipts/${encodeURIComponent(id)}/allocate/`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  const outgoing = result.ok
    ? NextResponse.json(result.data, { status: result.status })
    : NextResponse.json(
        backendErrorBody(result, "The allocation could not be created."),
        { status: result.status || 503 },
      );
  for (const cookie of response.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
