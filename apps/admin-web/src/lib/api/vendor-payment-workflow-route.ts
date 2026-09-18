import "server-only";

import { NextRequest, NextResponse } from "next/server";
import { backendErrorBody } from "@/lib/api/backend-error";
import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest } from "@/lib/auth/session";

export function vendorPaymentWorkflowRoute(
  action: "submit" | "approve" | "reject" | "pay",
) {
  return async function POST(
    request: NextRequest,
    context: { params: Promise<{ id: string }> },
  ) {
    if (!isSameOrigin(request))
      return NextResponse.json(
        { non_field_errors: ["Request origin is not allowed."] },
        { status: 403 },
      );
    const input = (await request.json().catch(() => ({}))) as Record<
      string,
      unknown
    >;
    const body: Record<string, string> = {};
    if (action === "reject" && typeof input.reason === "string")
      body.reason = input.reason;
    if (action === "pay") {
      if (typeof input.payment_account === "string")
        body.payment_account = input.payment_account;
      if (typeof input.payment_reference === "string")
        body.payment_reference = input.payment_reference;
    }
    const { id } = await context.params;
    const carrier = NextResponse.json({});
    const result = await authenticatedBackendRequest(
      request.cookies,
      carrier.cookies,
      `finance/vendor-payments/${encodeURIComponent(id)}/${action}/`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    );
    const outgoing = result.ok
      ? NextResponse.json(result.data ?? {}, { status: result.status })
      : NextResponse.json(
          backendErrorBody(result, "The Vendor Payment action failed."),
          { status: result.status || 503 },
        );
    for (const cookie of carrier.cookies.getAll()) outgoing.cookies.set(cookie);
    return outgoing;
  };
}
