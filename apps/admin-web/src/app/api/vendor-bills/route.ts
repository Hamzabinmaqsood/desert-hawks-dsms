import { NextRequest, NextResponse } from "next/server";
import {
  VENDOR_BILL_HEADER_FIELDS,
  type VendorBill,
  type VendorBillPage,
} from "@/features/vendor-bills/types";
import { backendErrorBody } from "@/lib/api/backend-error";
import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest } from "@/lib/auth/session";

const filters = new Set(["search", "status", "vendor", "ordering", "page"]);
const copyCookies = (source: NextResponse, target: NextResponse) => {
  for (const cookie of source.cookies.getAll()) target.cookies.set(cookie);
  return target;
};
export async function GET(request: NextRequest) {
  const carrier = NextResponse.json({});
  const query = new URLSearchParams();
  for (const [key, value] of request.nextUrl.searchParams)
    if (filters.has(key) && value) query.set(key, value);
  const result = await authenticatedBackendRequest<VendorBillPage>(
    request.cookies,
    carrier.cookies,
    `finance/vendor-bills/${query.size ? `?${query}` : ""}`,
  );
  return copyCookies(
    carrier,
    result.ok && result.data
      ? NextResponse.json(result.data)
      : NextResponse.json(
          backendErrorBody(result, "Vendor Bills could not be loaded."),
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
    "finance/vendor-bills/",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return copyCookies(
    carrier,
    result.ok && result.data
      ? NextResponse.json(result.data, { status: result.status })
      : NextResponse.json(
          backendErrorBody(result, "The Vendor Bill could not be created."),
          { status: result.status || 503 },
        ),
  );
}
