import { NextRequest } from "next/server";

import { proxyReferenceList } from "@/lib/api/reference-proxy";

export async function GET(request: NextRequest) {
  return proxyReferenceList(
    request,
    "billing/billing-rules/",
    [],
    "Billing rules could not be loaded.",
  );
}
