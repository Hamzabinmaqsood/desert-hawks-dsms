import { NextRequest, NextResponse } from "next/server";

import { authenticatedBackendRequest } from "@/lib/auth/session";

interface BackendBillingProfile {
  id: string;
  client: string;
  company: string;
  billing_name: string;
  currency: string;
  payment_terms_days: number;
  is_active: boolean;
}

interface BackendPage {
  count: number;
  next: string | null;
  previous: string | null;
  results: BackendBillingProfile[];
}

const allowed = new Set(["client", "company", "is_active"]);

// The backend BillingProfileSerializer uses `fields = "__all__"`, which
// includes billing contact details, internal notes, and default account
// FKs that the Invoice create form has no use for. Project down to the
// safe selection/display fields only before this reaches the browser.
function toSafeProfile(profile: BackendBillingProfile) {
  return {
    id: profile.id,
    client: profile.client,
    company: profile.company,
    billing_name: profile.billing_name,
    currency: profile.currency,
    payment_terms_days: profile.payment_terms_days,
    is_active: profile.is_active,
  };
}

export async function GET(request: NextRequest) {
  const response = NextResponse.json({}, { status: 200 });
  const query = new URLSearchParams();
  for (const [key, value] of request.nextUrl.searchParams)
    if (allowed.has(key) && value) query.set(key, value);
  const path = `billing/billing-profiles/${query.size ? `?${query}` : ""}`;
  const result = await authenticatedBackendRequest<BackendPage>(
    request.cookies,
    response.cookies,
    path,
  );
  const outgoing =
    result.ok && result.data
      ? NextResponse.json({
          ...result.data,
          results: result.data.results.map(toSafeProfile),
        })
      : NextResponse.json(
          {
            message:
              result.status === 403
                ? "You do not have access to this reference data."
                : result.status === 401
                  ? "Your session has expired."
                  : "Billing profiles could not be loaded.",
          },
          { status: result.status || 503 },
        );
  for (const cookie of response.cookies.getAll()) outgoing.cookies.set(cookie);
  return outgoing;
}
