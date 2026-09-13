import { NextRequest, NextResponse } from "next/server";
import type { ReceiptClient } from "@/features/receipts/types";
import { backendErrorBody } from "@/lib/api/backend-error";
import { authenticatedBackendRequest } from "@/lib/auth/session";

export async function GET(request: NextRequest) {
  const response = NextResponse.json({});
  const result = await authenticatedBackendRequest<{
    results: ReceiptClient[];
  }>(request.cookies, response.cookies, "billing/receipt-reference/clients/");
  const outgoing =
    result.ok && result.data
      ? NextResponse.json(result.data)
      : NextResponse.json(
          backendErrorBody(result, "Receipt clients could not be loaded."),
          { status: result.status || 503 },
        );
  for (const cookie of response.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
