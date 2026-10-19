import type { NextRequest } from "next/server";

import { proxyPeopleRequest } from "@/lib/api/people-proxy";

interface RouteContext {
  params: Promise<{ segments: string[] }>;
}

const handle = async (
  request: NextRequest,
  context: RouteContext,
  method: "GET" | "POST" | "PATCH",
) => proxyPeopleRequest(request, method, (await context.params).segments);

export const GET = (request: NextRequest, context: RouteContext) =>
  handle(request, context, "GET");
export const POST = (request: NextRequest, context: RouteContext) =>
  handle(request, context, "POST");
export const PATCH = (request: NextRequest, context: RouteContext) =>
  handle(request, context, "PATCH");
