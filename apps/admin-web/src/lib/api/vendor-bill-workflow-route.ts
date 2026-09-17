import "server-only";

import { NextRequest, NextResponse } from "next/server";

import { backendErrorBody } from "@/lib/api/backend-error";
import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest } from "@/lib/auth/session";

export function vendorBillWorkflowRoute(action: string, allowReason = false) {
  return async function POST(
    request: NextRequest,
    context: { params: Promise<{ id: string }> },
  ) {
    if (!isSameOrigin(request))
      return NextResponse.json(
        { non_field_errors: ["Request origin is not allowed."] },
        { status: 403 },
      );
    const { id } = await context.params;
    let body: Record<string, string> = {};
    if (allowReason) {
      const input = (await request.json().catch(() => ({}))) as Record<
        string,
        unknown
      >;
      body = { reason: typeof input.reason === "string" ? input.reason : "" };
    }
    const carrier = NextResponse.json({}, { status: 200 });
    const result = await authenticatedBackendRequest<unknown>(
      request.cookies,
      carrier.cookies,
      `finance/vendor-bills/${encodeURIComponent(id)}/${action}/`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    );
    const outgoing = result.ok
      ? NextResponse.json(result.data ?? {}, { status: result.status })
      : NextResponse.json(
          backendErrorBody(result, `The Vendor Bill could not be ${action}ed.`),
          { status: result.status || 503 },
        );
    for (const cookie of carrier.cookies.getAll()) outgoing.cookies.set(cookie);
    return outgoing;
  };
}
