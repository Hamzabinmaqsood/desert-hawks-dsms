import "server-only";

import { NextRequest, NextResponse } from "next/server";

import { backendErrorBody } from "@/lib/api/backend-error";
import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest } from "@/lib/auth/session";

/**
 * Builds a same-origin BFF handler for an Invoice workflow transition.
 *
 * Workflow transitions carry no business payload: the backend derives the
 * target status from the endpoint and the acting identity from the session.
 * The browser request body is therefore never read or forwarded, so a caller
 * cannot smuggle `status`, `approved_by`, `issued_by`, journal ids, or PDF
 * metadata into Django through these routes.
 */
export function invoiceWorkflowRoute(action: string, failure: string) {
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
    const response = NextResponse.json({}, { status: 200 });
    const result = await authenticatedBackendRequest<unknown>(
      request.cookies,
      response.cookies,
      `billing/invoices/${encodeURIComponent(id)}/${action}/`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      },
    );
    const outgoing = result.ok
      ? NextResponse.json(result.data ?? {}, { status: result.status })
      : NextResponse.json(backendErrorBody(result, failure), {
          status: result.status || 503,
        });
    for (const cookie of response.cookies.getAll())
      outgoing.cookies.set(cookie);
    return outgoing;
  };
}
