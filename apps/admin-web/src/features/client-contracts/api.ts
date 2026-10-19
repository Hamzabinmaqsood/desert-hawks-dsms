import { apiFetch } from "@/lib/api/client";
import type {
  Amendment,
  Client,
  ClientContact,
  CommercialTerms,
  Contract,
  ContractService,
  Industry,
  Page,
  ServiceLevel,
} from "./types";

const base = "/api/client-contracts";
const id = (value: string) => encodeURIComponent(value);
const mutation = <T>(
  path: string,
  method: "POST" | "PATCH",
  body: Record<string, unknown>,
) =>
  apiFetch<T>(`${base}/${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const listClients = (query: Record<string, string>) =>
  apiFetch<Page<Client>>(`${base}/clients`, { query });
export const getClient = (clientId: string) =>
  apiFetch<Client>(`${base}/clients/${id(clientId)}`);
export const saveClient = (
  clientId: string | null,
  body: Record<string, unknown>,
) =>
  mutation<Client>(
    `clients${clientId ? `/${id(clientId)}` : ""}`,
    clientId ? "PATCH" : "POST",
    body,
  );
export const activateClient = (clientId: string) =>
  mutation<Client>(`clients/${id(clientId)}/activate`, "POST", {});
export async function listIndustries() {
  const value = await apiFetch<Page<Industry> | Industry[]>(
    `${base}/industries`,
  );
  return Array.isArray(value) ? value : value.results;
}
export const listClientContacts = (clientId: string) =>
  apiFetch<Page<ClientContact>>(`${base}/client-contacts`, {
    query: { client: clientId },
  });
export const saveClientContact = (
  contactId: string | null,
  body: Record<string, unknown>,
) =>
  mutation<ClientContact>(
    `client-contacts${contactId ? `/${id(contactId)}` : ""}`,
    contactId ? "PATCH" : "POST",
    body,
  );

export const listContracts = (query: Record<string, string>) =>
  apiFetch<Page<Contract>>(`${base}/contracts`, { query });
export const getContract = (contractId: string) =>
  apiFetch<Contract>(`${base}/contracts/${id(contractId)}`);
export const saveContract = (
  contractId: string | null,
  body: Record<string, unknown>,
) =>
  mutation<Contract>(
    `contracts${contractId ? `/${id(contractId)}` : ""}`,
    contractId ? "PATCH" : "POST",
    body,
  );
export const contractAction = (
  contractId: string,
  action: "submit" | "approve" | "activate",
) => mutation<Contract>(`contracts/${id(contractId)}/${action}`, "POST", {});
export const listContractServices = (contractId: string) =>
  apiFetch<Page<ContractService>>(`${base}/contract-services`, {
    query: { contract: contractId },
  });
export const saveContractService = (
  serviceId: string | null,
  body: Record<string, unknown>,
) =>
  mutation<ContractService>(
    `contract-services${serviceId ? `/${id(serviceId)}` : ""}`,
    serviceId ? "PATCH" : "POST",
    body,
  );
export const listCommercialTerms = (contractId: string) =>
  apiFetch<Page<CommercialTerms>>(`${base}/commercial-terms`, {
    query: { contract: contractId },
  });
export const saveCommercialTerms = (
  termsId: string | null,
  body: Record<string, unknown>,
) =>
  mutation<CommercialTerms>(
    `commercial-terms${termsId ? `/${id(termsId)}` : ""}`,
    termsId ? "PATCH" : "POST",
    body,
  );
export const listAmendments = (contractId: string) =>
  apiFetch<Page<Amendment>>(`${base}/contract-amendments`, {
    query: { contract: contractId },
  });
export const listServiceLevels = (contractId: string) =>
  apiFetch<Page<ServiceLevel>>(`${base}/slas`, {
    query: { contract: contractId },
  });
