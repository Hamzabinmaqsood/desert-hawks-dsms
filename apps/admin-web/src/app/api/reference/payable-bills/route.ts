import { NextRequest, NextResponse } from "next/server";
import { backendErrorBody } from "@/lib/api/backend-error";
import { authenticatedBackendRequest } from "@/lib/auth/session";
export async function GET(request: NextRequest) {
  const carrier = NextResponse.json({});
  const result = await authenticatedBackendRequest(
    request.cookies,
    carrier.cookies,
    "finance/ap-reference/payable-bills/",
  );
  const outgoing = result.ok
    ? NextResponse.json(result.data ?? [])
    : NextResponse.json(
        backendErrorBody(result, "Payable Bills could not be loaded."),
        { status: result.status || 503 },
      );
  for (const cookie of carrier.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
