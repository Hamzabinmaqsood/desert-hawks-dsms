import { NextRequest, NextResponse } from "next/server";

import { authenticatedBackendDownload } from "@/lib/auth/session";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ id: string; attachmentId: string }> },
) {
  const { id, attachmentId } = await context.params;
  const carrier = NextResponse.json({}, { status: 200 });
  const backend = await authenticatedBackendDownload(
    request.cookies,
    carrier.cookies,
    `finance/vendor-bills/${encodeURIComponent(id)}/attachments/${encodeURIComponent(attachmentId)}/download/`,
  );
  if (!backend?.ok) {
    const outgoing = NextResponse.json(
      {
        non_field_errors: ["The supporting document could not be downloaded."],
      },
      { status: backend?.status ?? 401 },
    );
    for (const cookie of carrier.cookies.getAll()) outgoing.cookies.set(cookie);
    return outgoing;
  }
  const outgoing = new NextResponse(backend.body, {
    status: 200,
    headers: {
      "Content-Type":
        backend.headers.get("content-type") ?? "application/octet-stream",
      "Content-Disposition":
        backend.headers.get("content-disposition") ?? "attachment",
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
  for (const cookie of carrier.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
