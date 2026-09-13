import { NextRequest, NextResponse } from "next/server";
import type { Receipt } from "@/features/receipts/types";
import { backendErrorBody } from "@/lib/api/backend-error";
import { authenticatedBackendRequest } from "@/lib/auth/session";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const response = NextResponse.json({});
  const result = await authenticatedBackendRequest<Receipt>(
    request.cookies,
    response.cookies,
    `billing/receipts/${encodeURIComponent(id)}/`,
  );
  const outgoing =
    result.ok && result.data
      ? NextResponse.json(result.data)
      : NextResponse.json(
          backendErrorBody(result, "The receipt could not be loaded."),
          { status: result.status || 503 },
        );
  for (const cookie of response.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
