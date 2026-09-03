import { NextRequest, NextResponse } from "next/server";

import type { InvoiceDetail } from "@/features/invoices/types";
import { authenticatedBackendRequest } from "@/lib/auth/session";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const response = NextResponse.json({}, { status: 200 });
  const result = await authenticatedBackendRequest<InvoiceDetail>(
    request.cookies,
    response.cookies,
    `billing/invoices/${encodeURIComponent(id)}/`,
  );
  const outgoing =
    result.ok && result.data
      ? NextResponse.json(result.data)
      : NextResponse.json(
          {
            message:
              result.status === 404
                ? "Invoice not found."
                : result.status === 403
                  ? "You do not have access to invoices."
                  : result.status === 401
                    ? "Your session has expired."
                    : "The invoice could not be loaded.",
          },
          { status: result.status || 503 },
        );
  for (const cookie of response.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
