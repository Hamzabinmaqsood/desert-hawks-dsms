import { NextRequest, NextResponse } from "next/server";
import type { VendorPayableAccount } from "@/features/vendors/types";
import { backendErrorBody } from "@/lib/api/backend-error";
import { authenticatedBackendRequest } from "@/lib/auth/session";
export async function GET(request: NextRequest) {
  const carrier = NextResponse.json({});
  const result = await authenticatedBackendRequest<VendorPayableAccount[]>(
    request.cookies,
    carrier.cookies,
    "finance/ap-reference/payable-accounts/",
  );
  const outgoing =
    result.ok && result.data
      ? NextResponse.json(result.data)
      : NextResponse.json(
          backendErrorBody(result, "Payable accounts could not be loaded."),
          { status: result.status || 503 },
        );
  for (const item of carrier.cookies.getAll()) outgoing.cookies.set(item);
  return outgoing;
}
