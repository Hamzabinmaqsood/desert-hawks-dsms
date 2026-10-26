import "server-only";

import { NextRequest, NextResponse } from "next/server";

import { backendErrorBody } from "@/lib/api/backend-error";
import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest, loadSession } from "@/lib/auth/session";

type Product = "recruitment" | "leave" | "learning";
type Method = "GET" | "POST" | "PATCH";

const UUID = "[0-9a-fA-F-]{36}";
const configuration = {
  recruitment: {
    backend: "recruitment",
    resources:
      "manpower-requisitions|vacancies|candidates|applications|screenings|interviews|assessments|offers|onboarding",
    postCollections:
      "manpower-requisitions|vacancies|candidates|applications|screenings|interviews|assessments|offers|onboarding",
    actions:
      "submit|approve|reject|cancel|open|close|transition|issue|accept|begin-onboarding|ready-to-hire|hire",
    query: new Set([
      "search",
      "status",
      "branch",
      "department",
      "designation",
      "candidate",
      "vacancy",
      "application",
      "ordering",
      "page",
    ]),
    fields: new Set([
      "branch",
      "department",
      "designation",
      "employee_type",
      "employment_type",
      "requested_headcount",
      "required_by_date",
      "reason",
      "replacement_for_employee",
      "budget_reference",
      "approved_headcount",
      "manpower_requisition",
      "vacancy_code",
      "title",
      "description",
      "number_of_positions",
      "opening_date",
      "closing_date",
      "location_text",
      "is_public",
      "first_name",
      "middle_name",
      "last_name",
      "mobile_number",
      "alternate_mobile_number",
      "email",
      "city",
      "source_type",
      "notes",
      "candidate",
      "vacancy",
      "availability_date",
      "current_employer",
      "current_job_title",
      "total_experience_months",
      "application",
      "interview_type",
      "scheduled_at",
      "location",
      "assessment_type",
      "assessment_date",
      "maximum_score",
      "obtained_score",
      "result",
      "proposed_joining_date",
      "offer_expiry_date",
      "terms_summary",
      "proposed_employee_number",
      "employee_number",
    ]),
  },
  leave: {
    backend: "leave",
    resources:
      "types|me/requests|me/balances|manager/requests|team/calendar|holidays",
    postCollections: "me/requests",
    actions: "submit|request-cancellation|availability|approve|reject",
    query: new Set(["status", "leave_type", "employee", "ordering", "page"]),
    fields: new Set([
      "leave_type",
      "starts_at",
      "ends_at",
      "reason",
      "emergency_request",
    ]),
  },
  learning: {
    backend: "training",
    resources:
      "categories|courses|course-versions|qualification-types|employee-qualifications|programs|sessions|enrollments|assessments|completions|certificates|external-certifications",
    postCollections: "courses|sessions",
    actions:
      "activate|retire|schedule|open-enrollment|start|complete|enroll|assessment-result|finalize-result",
    query: new Set([
      "search",
      "status",
      "category",
      "course",
      "program",
      "session",
      "employee",
      "qualification_type",
      "ordering",
      "page",
    ]),
    fields: new Set([
      "category",
      "code",
      "title",
      "name",
      "description",
      "objective",
      "delivery_method",
      "duration_hours",
      "validity_months",
      "minimum_pass_percentage",
      "minimum_attendance_percentage",
      "requires_assessment",
      "produces_certificate",
      "is_mandatory_by_default",
      "course",
      "course_version",
      "program",
      "branch",
      "venue",
      "start_datetime",
      "end_datetime",
      "enrollment_deadline",
      "capacity",
      "lead_instructor",
      "notes",
      "employee",
      "allow_waitlist",
      "assessment",
      "score",
      "remarks",
    ]),
  },
} as const;

function copyCookies(source: NextResponse, target: NextResponse) {
  for (const cookie of source.cookies.getAll()) target.cookies.set(cookie);
  return target;
}

export async function proxyPeopleOperationsRequest(
  product: Product,
  request: NextRequest,
  method: Method,
  segments: string[],
) {
  const config = configuration[product];
  const path = `${segments.join("/")}/`;
  const collection = new RegExp(`^(${config.resources})/$`);
  const postCollection = new RegExp(`^(${config.postCollections})/$`);
  const detail = new RegExp(`^(${config.resources})/${UUID}/$`);
  const action = new RegExp(
    `^(${config.resources})/${UUID}/(${config.actions})/$|^me/requests/(availability)/$`,
  );
  const allowed =
    method === "GET"
      ? collection.test(path) || detail.test(path)
      : method === "PATCH"
        ? detail.test(path)
        : postCollection.test(path) || action.test(path);
  if (!allowed)
    return NextResponse.json(
      { message: `${product} route not found.` },
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

  let destination = `${config.backend}/${path}`;
  if (method === "GET" && collection.test(path)) {
    const query = new URLSearchParams();
    for (const [key, value] of request.nextUrl.searchParams)
      if (config.query.has(key) && value) query.set(key, value);
    if (product !== "leave") query.set("company", company);
    destination += `?${query}`;
  }

  let body: string | undefined;
  if (method !== "GET") {
    let input: Record<string, unknown>;
    try {
      input = await request.json();
    } catch {
      input = {};
    }
    const payload: Record<string, unknown> = {};
    for (const field of config.fields)
      if (input[field] !== undefined) payload[field] = input[field];
    for (const field of ["reason", "comments", "status", "approved_headcount"])
      if (input[field] !== undefined) payload[field] = input[field];
    if (method === "POST" && postCollection.test(path) && product !== "leave")
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
          backendErrorBody(result, `The ${product} request failed.`),
          {
            status: result.status || 503,
          },
        ),
  );
}
