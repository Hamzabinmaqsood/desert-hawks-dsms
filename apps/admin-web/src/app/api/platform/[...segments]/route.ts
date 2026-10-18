import type { NextRequest } from "next/server";

import { proxyPlatformRequest } from "@/lib/api/platform-proxy";

interface RouteContext {
  params: Promise<{ segments: string[] }>;
}

async function handle(
  request: NextRequest,
  context: RouteContext,
  method: "GET" | "POST" | "PUT",
) {
  const { segments } = await context.params;
  return proxyPlatformRequest(request, method, segments);
}

export const GET = (request: NextRequest, context: RouteContext) =>
  handle(request, context, "GET");
export const POST = (request: NextRequest, context: RouteContext) =>
  handle(request, context, "POST");
export const PUT = (request: NextRequest, context: RouteContext) =>
  handle(request, context, "PUT");
