import { NextRequest } from "next/server";

import { proxyReferenceList } from "@/lib/api/reference-proxy";

export async function GET(request: NextRequest) {
  return proxyReferenceList(
    request,
    "billing/invoice-reference/revenue-accounts/",
    [],
    "Revenue accounts could not be loaded.",
  );
}
