import { createServer } from "node:http";

const json = (response, status, body) => {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(body));
};

createServer((request, response) => {
  const path = request.url;
  if (path === "/api/v1/health/") return json(response, 200, { status: "ok" });
  if (path === "/api/v1/auth/login/" && request.method === "POST") {
    return json(response, 200, {
      access: "e2e-access",
      refresh: "e2e-refresh",
    });
  }
  if (path === "/api/v1/auth/refresh/" && request.method === "POST") {
    return json(response, 200, {
      access: "e2e-access-rotated",
      refresh: "e2e-refresh-rotated",
    });
  }
  if (path === "/api/v1/auth/logout/" && request.method === "POST") {
    response.writeHead(204);
    return response.end();
  }
  if (!request.headers.authorization?.startsWith("Bearer e2e-access")) {
    return json(response, 401, { detail: "Unauthenticated" });
  }
  if (path === "/api/v1/auth/me/") {
    return json(response, 200, {
      id: "00000000-0000-0000-0000-000000000001",
      email: "employee@example.test",
      first_name: "Test",
      last_name: "Employee",
      is_active: true,
      is_staff: false,
      is_superuser: false,
      last_login: null,
      date_joined: "2026-01-01T00:00:00Z",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
  }
  if (path === "/api/v1/auth/me/permissions/") {
    return json(response, 200, { permissions: ["billing.view_clientinvoice"] });
  }
  if (path === "/api/v1/auth/me/access-scopes/") {
    return json(response, 200, {
      is_superuser: false,
      accessible_company_ids: ["00000000-0000-0000-0000-000000000002"],
      accessible_region_ids: [],
      accessible_branch_ids: [],
      accessible_department_ids: [],
      accessible_operational_zone_ids: [],
      assignments: [],
    });
  }
  return json(response, 404, { detail: "Not found" });
}).listen(4010, "127.0.0.1");
