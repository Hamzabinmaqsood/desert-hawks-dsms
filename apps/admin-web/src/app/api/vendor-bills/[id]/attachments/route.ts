import { NextRequest, NextResponse } from "next/server";

import { backendErrorBody } from "@/lib/api/backend-error";
import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest } from "@/lib/auth/session";

async function proxy(request: NextRequest, id: string, init: RequestInit) {
  const carrier = NextResponse.json({}, { status: 200 });
  const result = await authenticatedBackendRequest(
    request.cookies,
    carrier.cookies,
    `finance/vendor-bills/${encodeURIComponent(id)}/attachments/`,
    init,
  );
  const outgoing = result.ok
    ? NextResponse.json(result.data ?? {}, { status: result.status })
    : NextResponse.json(
        backendErrorBody(result, "Supporting documents could not be loaded."),
        {
          status: result.status || 503,
        },
      );
  for (const cookie of carrier.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  return proxy(request, id, { method: "GET" });
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  if (!isSameOrigin(request))
    return NextResponse.json(
      { non_field_errors: ["Request origin is not allowed."] },
      { status: 403 },
    );
  const { id } = await context.params;
  const incoming = await request.formData();
  const file = incoming.get("file");
  if (!(file instanceof File))
    return NextResponse.json(
      { file: ["Attachment is required."] },
      { status: 400 },
    );
  const body = new FormData();
  body.set("file", file);
  return proxy(request, id, { method: "POST", body });
}
