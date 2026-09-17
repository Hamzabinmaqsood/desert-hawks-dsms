import { NextRequest, NextResponse } from "next/server";
import {
  VENDOR_BILL_HEADER_FIELDS,
  type VendorBill,
} from "@/features/vendor-bills/types";
import { backendErrorBody } from "@/lib/api/backend-error";
import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest } from "@/lib/auth/session";
const copy = (source: NextResponse, target: NextResponse) => {
  for (const cookie of source.cookies.getAll()) target.cookies.set(cookie);
  return target;
};
export async function GET(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const carrier = NextResponse.json({});
  const result = await authenticatedBackendRequest<VendorBill>(
    request.cookies,
    carrier.cookies,
    `finance/vendor-bills/${encodeURIComponent(id)}/`,
  );
  return copy(
    carrier,
    result.ok && result.data
      ? NextResponse.json(result.data)
      : NextResponse.json(
          backendErrorBody(result, "The Vendor Bill could not be loaded."),
          { status: result.status || 503 },
        ),
  );
}
export async function PATCH(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  if (!isSameOrigin(request))
    return NextResponse.json(
      { non_field_errors: ["Request origin is not allowed."] },
      { status: 403 },
    );
  const { id } = await context.params;
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { non_field_errors: ["A valid request body is required."] },
      { status: 400 },
    );
  }
  const payload: Record<string, unknown> = {};
  for (const key of VENDOR_BILL_HEADER_FIELDS)
    if (body[key] !== undefined) payload[key] = body[key];
  const carrier = NextResponse.json({});
  const result = await authenticatedBackendRequest<VendorBill>(
    request.cookies,
    carrier.cookies,
    `finance/vendor-bills/${encodeURIComponent(id)}/`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return copy(
    carrier,
    result.ok && result.data
      ? NextResponse.json(result.data)
      : NextResponse.json(
          backendErrorBody(result, "The Vendor Bill could not be updated."),
          { status: result.status || 503 },
        ),
  );
}
