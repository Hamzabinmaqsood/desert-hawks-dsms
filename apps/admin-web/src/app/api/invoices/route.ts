import { NextRequest, NextResponse } from "next/server";

import { authenticatedBackendRequest } from "@/lib/auth/session";
import type {
  InvoiceDetail,
  PaginatedResponse,
} from "@/features/invoices/types";

const allowed = new Set([
  "company",
  "client",
  "contract",
  "status",
  "invoice_type",
  "search",
  "ordering",
  "page",
]);

export async function GET(request: NextRequest) {
  const response = NextResponse.json({}, { status: 200 });
  const query = new URLSearchParams();
  for (const [key, value] of request.nextUrl.searchParams)
    if (allowed.has(key) && value) query.set(key, value);
  const path = `billing/invoices/${query.size ? `?${query}` : ""}`;
  const result = await authenticatedBackendRequest<
    PaginatedResponse<InvoiceDetail>
  >(request.cookies, response.cookies, path);
  const outgoing =
    result.ok && result.data
      ? NextResponse.json(result.data)
      : NextResponse.json(
          {
            message:
              result.status === 403
                ? "You do not have access to invoices."
                : result.status === 401
                  ? "Your session has expired."
                  : "Invoices could not be loaded.",
          },
          { status: result.status || 503 },
        );
  for (const cookie of response.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
