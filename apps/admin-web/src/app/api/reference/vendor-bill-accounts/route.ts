import { NextRequest, NextResponse } from "next/server";
import type { AccountOption } from "@/features/vendor-bills/types";
import { backendErrorBody } from "@/lib/api/backend-error";
import { authenticatedBackendRequest } from "@/lib/auth/session";
export async function GET(request: NextRequest) {
  const carrier = NextResponse.json({});
  const result = await authenticatedBackendRequest<AccountOption[]>(
    request.cookies,
    carrier.cookies,
    "finance/ap-reference/expense-accounts/",
  );
  const outgoing =
    result.ok && result.data
      ? NextResponse.json(result.data)
      : NextResponse.json(
          backendErrorBody(result, "Expense accounts could not be loaded."),
          { status: result.status || 503 },
        );
  for (const cookie of carrier.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
