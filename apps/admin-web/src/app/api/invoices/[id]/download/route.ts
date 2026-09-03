import { NextRequest, NextResponse } from "next/server";

import { authenticatedBackendDownload } from "@/lib/auth/session";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const cookieCarrier = NextResponse.json({}, { status: 200 });
  const backend = await authenticatedBackendDownload(
    request.cookies,
    cookieCarrier.cookies,
    `billing/invoices/${encodeURIComponent(id)}/download/`,
  );
  if (!backend?.ok) {
    const status = backend?.status ?? 401;
    const outgoing = NextResponse.json(
      {
        message:
          status === 404
            ? "Invoice PDF not found."
            : status === 403
              ? "You do not have permission to download this invoice."
              : status === 401
                ? "Your session has expired."
                : "The invoice PDF could not be downloaded.",
      },
      { status },
    );
    for (const cookie of cookieCarrier.cookies.getAll())
      outgoing.cookies.set(cookie);
    return outgoing;
  }
  const outgoing = new NextResponse(backend.body, {
    status: 200,
    headers: {
      "Content-Type": backend.headers.get("content-type") ?? "application/pdf",
      "Content-Disposition":
        backend.headers.get("content-disposition") ??
        "attachment; filename=invoice.pdf",
      "Cache-Control": "private, no-store",
    },
  });
  for (const cookie of cookieCarrier.cookies.getAll())
    outgoing.cookies.set(cookie);
  return outgoing;
}
