import { NextRequest, NextResponse } from "next/server";
import { backendErrorBody } from "@/lib/api/backend-error";
import { authenticatedBackendRequest } from "@/lib/auth/session";
export async function GET(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const carrier = NextResponse.json({});
  const result = await authenticatedBackendRequest(
    request.cookies,
    carrier.cookies,
    `finance/vendor-payments/${encodeURIComponent(id)}/`,
  );
  const outgoing = result.ok
    ? NextResponse.json(result.data ?? {})
    : NextResponse.json(
        backendErrorBody(result, "The Vendor Payment could not be loaded."),
        { status: result.status || 503 },
      );
  for (const cookie of carrier.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
