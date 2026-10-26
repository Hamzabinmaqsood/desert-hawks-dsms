import type { NextRequest } from "next/server";

import { proxyPeopleOperationsRequest } from "@/lib/api/people-operations-proxy";

interface Context {
  params: Promise<{ segments: string[] }>;
}
const handle = async (
  request: NextRequest,
  context: Context,
  method: "GET" | "POST" | "PATCH",
) =>
  proxyPeopleOperationsRequest(
    "learning",
    request,
    method,
    (await context.params).segments,
  );
export const GET = (request: NextRequest, context: Context) =>
  handle(request, context, "GET");
export const POST = (request: NextRequest, context: Context) =>
  handle(request, context, "POST");
export const PATCH = (request: NextRequest, context: Context) =>
  handle(request, context, "PATCH");
