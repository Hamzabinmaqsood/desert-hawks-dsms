import { NextRequest, NextResponse } from "next/server";
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
  const response = NextResponse.json({});
  const result = await authenticatedBackendRequest(
    request.cookies,
    response.cookies,
    `billing/receipts/${encodeURIComponent(id)}/confirm/`,
    { method: "POST" },
  );
  const outgoing = result.ok
    ? NextResponse.json(result.data)
    : NextResponse.json(
        backendErrorBody(result, "The receipt could not be confirmed."),
        { status: result.status || 503 },
      );
  for (const cookie of response.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
