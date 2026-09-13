import { NextRequest, NextResponse } from "next/server";
import type { EligibleInvoice } from "@/features/receipts/types";
import { backendErrorBody } from "@/lib/api/backend-error";
import { authenticatedBackendRequest } from "@/lib/auth/session";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const response = NextResponse.json({});
  const result = await authenticatedBackendRequest<EligibleInvoice[]>(
    request.cookies,
    response.cookies,
    `billing/receipts/${encodeURIComponent(id)}/eligible-invoices/`,
  );
  const outgoing =
    result.ok && result.data
      ? NextResponse.json(result.data)
      : NextResponse.json(
          backendErrorBody(result, "Eligible invoices could not be loaded."),
          { status: result.status || 503 },
        );
  for (const cookie of response.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
