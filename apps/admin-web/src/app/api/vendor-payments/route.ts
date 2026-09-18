import { NextRequest, NextResponse } from "next/server";
import { VENDOR_PAYMENT_FIELDS } from "@/features/vendor-payments/types";
import { backendErrorBody } from "@/lib/api/backend-error";
import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest } from "@/lib/auth/session";

const copy = (source: NextResponse, target: NextResponse) => {
  for (const cookie of source.cookies.getAll()) target.cookies.set(cookie);
  return target;
};
export async function GET(request: NextRequest) {
  const query = new URLSearchParams();
  for (const [key, value] of request.nextUrl.searchParams)
    if (
      [
        "search",
        "status",
        "payment_status",
        "vendor_bill",
        "ordering",
        "page",
      ].includes(key) &&
      value
    )
      query.set(key, value);
  const carrier = NextResponse.json({});
  const result = await authenticatedBackendRequest(
    request.cookies,
    carrier.cookies,
    `finance/vendor-payments/${query.size ? `?${query}` : ""}`,
  );
  return copy(
    carrier,
    result.ok
      ? NextResponse.json(result.data ?? {})
      : NextResponse.json(
          backendErrorBody(result, "Vendor Payments could not be loaded."),
          { status: result.status || 503 },
        ),
  );
}
export async function POST(request: NextRequest) {
  if (!isSameOrigin(request))
    return NextResponse.json(
      { non_field_errors: ["Request origin is not allowed."] },
      { status: 403 },
    );
  const input = (await request.json().catch(() => ({}))) as Record<
    string,
    unknown
  >;
  const body: Record<string, unknown> = {};
  for (const field of VENDOR_PAYMENT_FIELDS)
    if (input[field] !== undefined) body[field] = input[field];
  const carrier = NextResponse.json({});
  const result = await authenticatedBackendRequest(
    request.cookies,
    carrier.cookies,
    "finance/vendor-payments/",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  return copy(
    carrier,
    result.ok
      ? NextResponse.json(result.data ?? {}, { status: result.status })
      : NextResponse.json(
          backendErrorBody(result, "The Vendor Payment could not be created."),
          { status: result.status || 503 },
        ),
  );
}
