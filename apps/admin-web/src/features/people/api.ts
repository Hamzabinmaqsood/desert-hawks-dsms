import { apiFetch } from "@/lib/api/client";
import type {
  AssignmentHistory,
  EmergencyContact,
  Employee,
  EmployeeAddress,
  EmployeeDocument,
  EmployeeListItem,
  OrganizationReference,
  Page,
  StatusHistory,
} from "./types";

const base = "/api/people";
const id = (value: string) => encodeURIComponent(value);

export const listEmployees = (query: Record<string, string>) =>
  apiFetch<Page<EmployeeListItem>>(`${base}/employees`, { query });
export const getEmployee = (employeeId: string) =>
  apiFetch<Employee>(`${base}/employees/${id(employeeId)}`);
export const createEmployee = (body: Record<string, unknown>) =>
  apiFetch<Employee>(`${base}/employees`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
export const updateEmployee = (
  employeeId: string,
  body: Record<string, unknown>,
) =>
  apiFetch<Employee>(`${base}/employees/${id(employeeId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
export const employeeAction = (
  employeeId: string,
  action: string,
  body: Record<string, unknown>,
) =>
  apiFetch<Employee>(`${base}/employees/${id(employeeId)}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export async function listReferences(
  kind: "branches" | "departments" | "designations",
) {
  const result = await apiFetch<
    Page<OrganizationReference> | OrganizationReference[]
  >(`${base}/${kind}`);
  return Array.isArray(result) ? result : result.results;
}

export const listAddresses = (employeeId: string) =>
  apiFetch<EmployeeAddress[]>(`${base}/employees/${id(employeeId)}/addresses`);
export const saveAddress = (
  employeeId: string,
  addressId: string | null,
  body: Record<string, unknown>,
) =>
  apiFetch<EmployeeAddress>(
    `${base}/employees/${id(employeeId)}/addresses${addressId ? `/${id(addressId)}` : ""}`,
    {
      method: addressId ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
export const listEmergencyContacts = (employeeId: string) =>
  apiFetch<EmergencyContact[]>(
    `${base}/employees/${id(employeeId)}/emergency-contacts`,
  );
export const saveEmergencyContact = (
  employeeId: string,
  contactId: string | null,
  body: Record<string, unknown>,
) =>
  apiFetch<EmergencyContact>(
    `${base}/employees/${id(employeeId)}/emergency-contacts${contactId ? `/${id(contactId)}` : ""}`,
    {
      method: contactId ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
export const listStatusHistory = (employeeId: string) =>
  apiFetch<StatusHistory[]>(
    `${base}/employees/${id(employeeId)}/status-history`,
  );
export const listAssignmentHistory = (employeeId: string) =>
  apiFetch<AssignmentHistory[]>(
    `${base}/employees/${id(employeeId)}/assignment-history`,
  );
export const listEmployeeDocuments = (employeeId: string) =>
  apiFetch<EmployeeDocument[] | Page<EmployeeDocument>>(
    `${base}/employees/${id(employeeId)}/documents`,
  ).then((value) => (Array.isArray(value) ? value : value.results));
