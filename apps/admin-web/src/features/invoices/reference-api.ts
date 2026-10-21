import { apiFetch } from "@/lib/api/client";

import type {
  AccountOption,
  BillingProfile,
  BillingRuleOption,
  Contract,
  ContractServiceOption,
  SiteOption,
} from "./types";

function listOf<T>(body: unknown): T[] {
  if (Array.isArray(body)) return body as T[];
  if (
    body &&
    typeof body === "object" &&
    Array.isArray((body as { results?: unknown }).results)
  )
    return (body as { results: T[] }).results;
  return [];
}

export async function listBillingProfiles(
  query: Record<string, string> = { is_active: "true" },
) {
  return listOf<BillingProfile>(
    await apiFetch("/api/reference/billing-profiles", {
      query,
    }),
  );
}

export async function listContracts() {
  return listOf<Contract>(await apiFetch("/api/reference/contracts"));
}

export async function listContractServices() {
  return listOf<ContractServiceOption>(
    await apiFetch("/api/reference/contract-services"),
  );
}

export async function listSites() {
  return listOf<SiteOption>(await apiFetch("/api/reference/sites"));
}

export async function listBillingRules() {
  return listOf<BillingRuleOption>(
    await apiFetch("/api/reference/billing-rules"),
  );
}

export async function listAccounts() {
  return listOf<AccountOption>(await apiFetch("/api/reference/accounts"));
}
