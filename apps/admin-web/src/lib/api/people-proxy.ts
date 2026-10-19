import { NextRequest, NextResponse } from "next/server";

import { backendErrorBody } from "@/lib/api/backend-error";
import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest, loadSession } from "@/lib/auth/session";

const UUID = "[0-9a-fA-F-]{36}";
const EMPLOYEE = new RegExp(`^employees(?:/${UUID})?/$`);
const EMPLOYEE_COLLECTION = /^employees\/$/;
const EMPLOYEE_CHILD = new RegExp(
  `^employees/${UUID}/(status-history|assignment-history|addresses|emergency-contacts)/$`,
);
const EMPLOYEE_CHILD_DETAIL = new RegExp(
  `^employees/${UUID}/(addresses|emergency-contacts)/${UUID}/$`,
);
const EMPLOYEE_ACTION = new RegExp(
  `^employees/${UUID}/(activate|leave|return-from-leave|suspend|reinstate|resign|terminate|retire|mark-absconded|change-assignment)/$`,
);
const REFERENCE = /^(branches|departments|designations)\/$/;
const DOCUMENTS = new RegExp(`^employees/${UUID}/documents/$`);

const EMPLOYEE_FIELDS = new Set([
  "employee_number",
  "first_name",
  "middle_name",
  "last_name",
  "preferred_name",
  "father_or_spouse_name",
  "gender",
  "date_of_birth",
  "marital_status",
  "nationality",
  "national_identity_number",
  "national_identity_expiry",
  "personal_email",
  "mobile_number",
  "alternate_mobile_number",
  "employee_type",
  "employment_type",
  "joining_date",
  "confirmation_date",
  "probation_end_date",
  "branch",
  "department",
  "designation",
  "notes",
]);
const ADDRESS_FIELDS = new Set([
  "address_type",
  "address_line_1",
  "address_line_2",
  "city",
  "province_or_state",
  "postal_code",
  "country_code",
  "is_primary",
]);
const CONTACT_FIELDS = new Set([
  "name",
  "relationship",
  "mobile_number",
  "alternate_mobile_number",
  "address",
  "is_primary",
]);
const STATUS_FIELDS = new Set(["effective_date", "exit_date", "reason"]);
const ASSIGNMENT_FIELDS = new Set([
  "effective_from",
  "branch",
  "department",
  "designation",
  "reason",
]);
const LIST_FILTERS = new Set([
  "search",
  "employment_status",
  "branch",
  "department",
  "designation",
  "employee_type",
  "employment_type",
  "ordering",
  "page",
]);

function copyCookies(source: NextResponse, target: NextResponse) {
  for (const cookie of source.cookies.getAll()) target.cookies.set(cookie);
  return target;
}

function fieldsFor(path: string) {
  if (path.includes("/addresses")) return ADDRESS_FIELDS;
  if (path.includes("/emergency-contacts")) return CONTACT_FIELDS;
  if (path.endsWith("/change-assignment/")) return ASSIGNMENT_FIELDS;
  if (EMPLOYEE_ACTION.test(path)) return STATUS_FIELDS;
  return EMPLOYEE_FIELDS;
}

function backendPath(path: string) {
  if (REFERENCE.test(path)) return `organization/${path}`;
  if (DOCUMENTS.test(path)) return `documents/${path}`;
  return `workforce/${path}`;
}

export async function proxyPeopleRequest(
  request: NextRequest,
  method: "GET" | "POST" | "PATCH",
  segments: string[],
) {
  const path = `${segments.join("/")}/`;
  const allowed =
    method === "GET"
      ? EMPLOYEE.test(path) ||
        EMPLOYEE_CHILD.test(path) ||
        EMPLOYEE_CHILD_DETAIL.test(path) ||
        REFERENCE.test(path) ||
        DOCUMENTS.test(path)
      : method === "POST"
        ? EMPLOYEE_COLLECTION.test(path) ||
          EMPLOYEE_ACTION.test(path) ||
          /\/(addresses|emergency-contacts)\/$/.test(path)
        : EMPLOYEE.test(path) || EMPLOYEE_CHILD_DETAIL.test(path);
  if (!allowed)
    return NextResponse.json(
      { message: "People route not found." },
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

  let destination = backendPath(path);
  if (method === "GET") {
    const query = new URLSearchParams();
    if (EMPLOYEE_COLLECTION.test(path)) {
      for (const [key, value] of request.nextUrl.searchParams)
        if (LIST_FILTERS.has(key) && value) query.set(key, value);
      query.set("company", company);
    } else if (REFERENCE.test(path)) {
      query.set("company", company);
      query.set("page_size", "200");
      query.set("ordering", "name");
    }
    if (query.size) destination += `?${query}`;
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
    const payload: Record<string, unknown> = {};
    for (const field of fieldsFor(path))
      if (input[field] !== undefined) payload[field] = input[field];
    if (method === "POST" && EMPLOYEE_COLLECTION.test(path))
      payload.company = company;
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
          backendErrorBody(
            result,
            "The People request could not be completed.",
          ),
          { status: result.status || 503 },
        ),
  );
}
