import "server-only";

import { NextRequest, NextResponse } from "next/server";

import { backendErrorBody } from "@/lib/api/backend-error";
import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest, loadSession } from "@/lib/auth/session";

const UUID = "[0-9a-fA-F-]{36}";
const RESOURCE = "purchase-requisitions|purchase-orders|purchase-receipts";
const DETAIL = new RegExp(`^(${RESOURCE})(?:/${UUID})?/$`);
const COLLECTION = new RegExp(`^(${RESOURCE})/$`);
const ACTION = new RegExp(
  `^(purchase-requisitions|purchase-orders)/${UUID}/(submit|approve|reject)/$|^purchase-receipts/${UUID}/confirm/$`,
);
const FIELDS: Record<string, readonly string[]> = {
  "purchase-requisitions": [
    "branch",
    "department",
    "cost_center",
    "requisition_number",
    "required_date",
    "purpose",
    "lines",
  ],
  "purchase-orders": [
    "requisition",
    "vendor",
    "order_number",
    "order_date",
    "lines",
  ],
  "purchase-receipts": [
    "purchase_order",
    "receipt_number",
    "receipt_date",
    "receipt_type",
    "lines",
  ],
};
const QUERY = new Set([
  "search",
  "status",
  "vendor",
  "requisition",
  "purchase_order",
  "receipt_type",
  "ordering",
  "page",
]);

function copyCookies(source: NextResponse, target: NextResponse) {
  for (const cookie of source.cookies.getAll()) target.cookies.set(cookie);
  return target;
}

export async function proxyProcurementRequest(
  request: NextRequest,
  method: "GET" | "POST" | "PATCH",
  segments: string[],
) {
  const path = `${segments.join("/")}/`;
  const resource = segments[0];
  const allowed =
    method === "GET"
      ? DETAIL.test(path)
      : method === "POST"
        ? COLLECTION.test(path) || ACTION.test(path)
        : DETAIL.test(path) && segments.length === 2;
  if (!allowed)
    return NextResponse.json(
      { message: "Procurement route not found." },
      { status: 404 },
    );
  if (method !== "GET" && !isSameOrigin(request))
    return NextResponse.json(
      { non_field_errors: ["Request origin is not allowed."] },
      { status: 403 },
    );

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

  let destination = `finance/${path}`;
  if (method === "GET" && segments.length === 1) {
    const query = new URLSearchParams();
    for (const [key, value] of request.nextUrl.searchParams)
      if (QUERY.has(key) && value) query.set(key, value);
    query.set("company", company);
    destination += `?${query}`;
  }

  let body: string | undefined;
  if (method !== "GET") {
    let input: Record<string, unknown>;
    try {
      input = await request.json();
    } catch {
      return NextResponse.json(
        { non_field_errors: ["A valid request body is required."] },
        { status: 400 },
      );
    }
    if (ACTION.test(path)) {
      body = JSON.stringify(
        path.endsWith("/reject/") ? { reason: input.reason ?? "" } : {},
      );
    } else {
      const payload: Record<string, unknown> = {};
      for (const field of FIELDS[resource] ?? [])
        if (input[field] !== undefined) payload[field] = input[field];
      if (method === "POST") payload.company = company;
      body = JSON.stringify(payload);
    }
  }
  const result = await authenticatedBackendRequest<unknown>(
    request.cookies,
    carrier.cookies,
    destination,
    {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body,
    },
  );
  return copyCookies(
    carrier,
    result.ok && result.data !== null
      ? NextResponse.json(result.data, { status: result.status })
      : NextResponse.json(
          backendErrorBody(result, "The Procurement request failed."),
          { status: result.status || 503 },
        ),
  );
}
