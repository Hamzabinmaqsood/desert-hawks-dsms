import "server-only";

import type { BackendResult } from "@/lib/auth/backend";

const ENVELOPE_KEYS = new Set(["code", "detail", "errors"]);

function asStringList(value: unknown): string[] {
  return (Array.isArray(value) ? value : [value]).filter(
    (item): item is string => typeof item === "string",
  );
}

export function backendErrorBody(
  result: Pick<BackendResult<unknown>, "status" | "data">,
  fallback: string,
): Record<string, string[]> {
  const nonField: string[] = [];
  const fields: Record<string, string[]> = {};
  const data =
    result.data &&
    typeof result.data === "object" &&
    !Array.isArray(result.data)
      ? (result.data as Record<string, unknown>)
      : null;

  if (
    result.status === 403 &&
    data?.code === "module_not_enabled" &&
    Array.isArray(data.required_modules)
  ) {
    return {
      code: ["module_not_enabled"],
      non_field_errors: ["This module is not enabled for this Company."],
    };
  }

  if (data) {
    for (const [key, value] of Object.entries(data)) {
      if (ENVELOPE_KEYS.has(key)) continue;
      const messages = asStringList(value);
      if (messages.length) fields[key] = messages;
    }
    if (Array.isArray(data.detail)) nonField.push(...asStringList(data.detail));
    if (Array.isArray(data.errors)) nonField.push(...asStringList(data.errors));
  }

  if (!nonField.length && !Object.keys(fields).length) {
    nonField.push(
      result.status === 401
        ? "Your session has expired."
        : result.status === 403
          ? "You do not have permission to perform this action."
          : result.status === 404
            ? "The requested invoice could not be found."
            : result.status === 409
              ? "This change conflicts with the current invoice state. Refresh and try again."
              : fallback,
    );
  }

  return { non_field_errors: nonField, ...fields };
}
