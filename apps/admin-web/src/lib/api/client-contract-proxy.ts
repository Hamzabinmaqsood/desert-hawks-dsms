import { NextRequest, NextResponse } from "next/server";

import { backendErrorBody } from "@/lib/api/backend-error";
import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest, loadSession } from "@/lib/auth/session";

const UUID = "[0-9a-fA-F-]{36}";
const RESOURCE =
  "industries|clients|client-contacts|contracts|contract-services|commercial-terms|contract-amendments|slas";
const DETAIL = new RegExp(`^(${RESOURCE})(?:/${UUID})?/$`);
const COLLECTION = new RegExp(`^(${RESOURCE})/$`);
const ACTION = new RegExp(
  `^(clients/${UUID}/activate|contracts/${UUID}/(submit|approve|activate))/$`,
);

const FIELDS: Record<string, readonly string[]> = {
  industries: ["code", "name", "is_active"],
  clients: [
    "client_code",
    "legal_name",
    "trade_name",
    "industry",
    "registration_number",
    "tax_number",
    "website",
    "main_email",
    "main_phone",
    "billing_address",
    "head_office_address",
    "city",
    "province_or_state",
    "country_code",
    "notes",
    "account_manager",
  ],
  "client-contacts": [
    "client",
    "name",
    "designation",
    "department",
    "email",
    "mobile_number",
    "office_phone",
    "contact_type",
    "is_primary",
    "notes",
    "is_active",
  ],
  contracts: [
    "client",
    "contract_number",
    "contract_type",
    "title",
    "description",
    "signed_date",
    "start_date",
    "end_date",
    "notice_period_days",
    "auto_renew",
    "currency",
    "client_reference",
    "purchase_order_reference",
    "internal_reference",
    "primary_client_contact",
    "account_manager",
  ],
  "contract-services": [
    "contract",
    "service_type",
    "name",
    "description",
    "start_date",
    "end_date",
    "is_active",
  ],
  "commercial-terms": [
    "contract",
    "billing_frequency",
    "agreed_contract_value",
    "monthly_service_value",
    "payment_terms_days",
    "security_deposit",
    "notes",
  ],
  slas: [
    "contract",
    "sla_type",
    "name",
    "description",
    "target_value",
    "target_unit",
    "effective_from",
    "effective_to",
    "is_active",
  ],
};
const QUERY = new Set([
  "search",
  "status",
  "industry",
  "client",
  "contract",
  "contract_type",
  "contact_type",
  "service_type",
  "is_active",
  "site",
  "site__isnull",
  "ordering",
  "page",
]);

function copyCookies(source: NextResponse, target: NextResponse) {
  for (const cookie of source.cookies.getAll()) target.cookies.set(cookie);
  return target;
}

export async function proxyClientContractRequest(
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
        ? (COLLECTION.test(path) && resource !== "contract-amendments") ||
          ACTION.test(path)
        : DETAIL.test(path) &&
          segments.length === 2 &&
          resource !== "contract-amendments";
  if (!allowed)
    return NextResponse.json(
      { message: "Client and Contract route not found." },
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

  let destination = `contracts/${path}`;
  if (method === "GET" && segments.length === 1) {
    const query = new URLSearchParams();
    for (const [key, value] of request.nextUrl.searchParams)
      if (QUERY.has(key) && value) query.set(key, value);
    if (["industries", "clients", "contracts"].includes(resource))
      query.set("company", company);
    if (resource === "slas") query.set("site__isnull", "true");
    if (query.size) destination += `?${query}`;
  }

  let body: string | undefined;
  if (method !== "GET" && !ACTION.test(path)) {
    let input: Record<string, unknown>;
    try {
      input = await request.json();
    } catch {
      return NextResponse.json(
        { non_field_errors: ["A valid request body is required."] },
        { status: 400 },
      );
    }
    const payload: Record<string, unknown> = {};
    for (const field of FIELDS[resource] ?? [])
      if (input[field] !== undefined) payload[field] = input[field];
    if (
      method === "POST" &&
      ["industries", "clients", "contracts"].includes(resource)
    )
      payload.company = company;
    body = JSON.stringify(payload);
  }
  if (method === "POST" && ACTION.test(path)) body = "{}";

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
          backendErrorBody(
            result,
            "The Client and Contract request could not be completed.",
          ),
          { status: result.status || 503 },
        ),
  );
}
