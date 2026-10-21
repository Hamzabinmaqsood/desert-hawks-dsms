import "server-only";

import { NextRequest, NextResponse } from "next/server";

import { backendErrorBody } from "@/lib/api/backend-error";
import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest, loadSession } from "@/lib/auth/session";

const UUID = "[0-9a-fA-F-]{36}";
const READ_RESOURCE =
  "assets|items|categories|stores|issues|movements|stock-accounts|procurement-registrations";
const READ = new RegExp(`^(${READ_RESOURCE})(?:/${UUID})?/$`);
const REGISTRATION = /^procurement-registrations\/$/;
const ISSUE_FROM_ASSET = /^issues\/from-asset\/$/;
const ISSUE_ACTION = new RegExp(
  `^issues/${UUID}/(submit|approve|issue|return)/$`,
);
const ASSET_DETAIL = new RegExp(`^assets/${UUID}/$`);
const MUTATION_FIELDS: Record<string, readonly string[]> = {
  assets: ["warranty_expires_on", "expected_retirement_on", "notes"],
  "procurement-registrations": [
    "receipt_line",
    "asset_item",
    "destination_store",
    "idempotency_key",
    "quantity",
    "assets",
  ],
  "from-asset": [
    "asset",
    "issue_number",
    "issue_type",
    "employee",
    "branch",
    "expected_return_at",
    "purpose",
    "notes",
  ],
  return: [
    "return_number",
    "return_condition",
    "returned_at",
    "damage_notes",
    "requires_maintenance",
    "notes",
  ],
};
const QUERY = new Set([
  "search",
  "status",
  "condition",
  "item",
  "current_branch",
  "current_employee",
  "asset",
  "movement_type",
  "ordering",
  "page",
  "is_active",
]);

function copyCookies(source: NextResponse, target: NextResponse) {
  for (const cookie of source.cookies.getAll()) target.cookies.set(cookie);
  return target;
}

export async function proxyAssetRequest(
  request: NextRequest,
  method: "GET" | "POST" | "PATCH",
  segments: string[],
) {
  const path = `${segments.join("/")}/`;
  const allowed =
    method === "GET"
      ? READ.test(path)
      : method === "POST"
        ? REGISTRATION.test(path) ||
          ISSUE_FROM_ASSET.test(path) ||
          ISSUE_ACTION.test(path)
        : ASSET_DETAIL.test(path);
  if (!allowed)
    return NextResponse.json(
      { message: "Asset route not found." },
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

  let destination = `assets/${path}`;
  if (method === "GET" && segments.length === 1) {
    const query = new URLSearchParams();
    for (const [key, value] of request.nextUrl.searchParams)
      if (QUERY.has(key) && value) {
        const backendKey =
          key === "asset" && segments[0] === "issues"
            ? "lines__serialized_asset"
            : key;
        query.set(backendKey, value);
      }
    if (["assets", "items", "categories", "stores"].includes(segments[0]))
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
    const key = REGISTRATION.test(path)
      ? "procurement-registrations"
      : ISSUE_FROM_ASSET.test(path)
        ? "from-asset"
        : path.endsWith("/return/")
          ? "return"
          : path.startsWith("assets/")
            ? "assets"
            : "";
    const payload: Record<string, unknown> = {};
    for (const field of MUTATION_FIELDS[key] ?? [])
      if (input[field] !== undefined) payload[field] = input[field];
    body = JSON.stringify(payload);
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
          backendErrorBody(result, "The Asset request failed."),
          { status: result.status || 503 },
        ),
  );
}
