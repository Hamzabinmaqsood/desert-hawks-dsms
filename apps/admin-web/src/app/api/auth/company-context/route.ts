import { NextRequest, NextResponse } from "next/server";

import { isSameOrigin } from "@/lib/auth/origin";
import { authenticatedBackendRequest } from "@/lib/auth/session";
import type { CompanyContextBootstrap } from "@/lib/auth/types";

export async function PUT(request: NextRequest) {
  if (!isSameOrigin(request)) {
    return NextResponse.json(
      { message: "Request origin is not allowed." },
      { status: 403 },
    );
  }
  let companyId = "";
  try {
    const body = (await request.json()) as { company_id?: unknown };
    if (typeof body.company_id === "string") companyId = body.company_id;
  } catch {
    // Normalized below.
  }
  if (!companyId) {
    return NextResponse.json({ message: "Select a Company." }, { status: 400 });
  }

  const cookieResponse = NextResponse.json({}, { status: 200 });
  const result = await authenticatedBackendRequest<CompanyContextBootstrap>(
    request.cookies,
    cookieResponse.cookies,
    "auth/company-context/",
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_id: companyId }),
    },
  );
  const status = result.ok
    ? 200
    : result.status === 400 || result.status === 404
      ? result.status
      : result.status === 401
        ? 401
        : 503;
  const response = NextResponse.json(
    result.ok && result.data
      ? {
          companies: result.data.companies,
          selected_company: result.data.selected_company,
          selection_required: result.data.selection_required,
        }
      : {
          message:
            status === 404
              ? "Company is unavailable."
              : status === 401
                ? "Your session has expired."
                : status === 400
                  ? "Select a valid Company."
                  : "Company switching is temporarily unavailable.",
        },
    { status },
  );
  for (const cookie of cookieResponse.cookies.getAll())
    response.cookies.set(cookie);
  return response;
}
