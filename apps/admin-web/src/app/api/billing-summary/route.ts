import { NextRequest, NextResponse } from "next/server";

import { backendErrorBody } from "@/lib/api/backend-error";
import { authenticatedBackendRequest, loadSession } from "@/lib/auth/session";

function copyCookies(source: NextResponse, target: NextResponse) {
  for (const cookie of source.cookies.getAll()) target.cookies.set(cookie);
  return target;
}

export async function GET(request: NextRequest) {
  const carrier = NextResponse.json({});
  const identity = await loadSession(request.cookies, carrier.cookies);
  const company = identity.session?.company_context.selected_company?.id;
  if (!company)
    return copyCookies(
      carrier,
      NextResponse.json(
        { message: "Select a Company to continue." },
        { status: 409 },
      ),
    );
  const result = await authenticatedBackendRequest<{
    ageing: Record<string, string>;
  }>(
    request.cookies,
    carrier.cookies,
    `billing/dashboard/?company=${encodeURIComponent(company)}`,
  );
  return copyCookies(
    carrier,
    result.ok && result.data
      ? NextResponse.json(result.data, { status: result.status })
      : NextResponse.json(
          backendErrorBody(
            result,
            "The receivables summary could not be loaded.",
          ),
          { status: result.status || 503 },
        ),
  );
}
