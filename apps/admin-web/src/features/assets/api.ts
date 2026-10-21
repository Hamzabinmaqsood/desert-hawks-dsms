import { apiFetch } from "@/lib/api/client";
import type { PurchaseReceipt } from "@/features/procurement/types";
import type {
  AssetCategory,
  AssetIssue,
  AssetItem,
  AssetMovement,
  AssetRecord,
  AssetStore,
  BranchOption,
  EmployeeOption,
  Page,
  RegistrationResult,
} from "./types";

const base = "/api/assets";
const id = (value: string) => encodeURIComponent(value);
export const listAssets = (query: Record<string, string>) =>
  apiFetch<Page<AssetRecord>>(`${base}/assets`, { query });
export const getAsset = (value: string) =>
  apiFetch<AssetRecord>(`${base}/assets/${id(value)}`);
export const updateAsset = (value: string, body: Record<string, unknown>) =>
  apiFetch<AssetRecord>(`${base}/assets/${id(value)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
export const listAssetItems = () =>
  apiFetch<Page<AssetItem>>(`${base}/items`, {
    query: { is_active: "true", ordering: "item_code" },
  }).then((value) => value.results);
export const listAssetCategories = () =>
  apiFetch<Page<AssetCategory>>(`${base}/categories`, {
    query: { is_active: "true", ordering: "code" },
  }).then((value) => value.results);
export const listAssetStores = () =>
  apiFetch<Page<AssetStore>>(`${base}/stores`, {
    query: { is_active: "true", ordering: "code" },
  }).then((value) => value.results);
export const listAssetMovements = (asset: string) =>
  apiFetch<Page<AssetMovement>>(`${base}/movements`, { query: { asset } }).then(
    (value) => value.results,
  );
export const listAssetIssues = (asset: string) =>
  apiFetch<Page<AssetIssue>>(`${base}/issues`, { query: { asset } }).then(
    (value) => value.results,
  );
export const createAssetIssue = (body: Record<string, unknown>) =>
  apiFetch<AssetIssue>(`${base}/issues/from-asset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
export const assetIssueAction = (
  issue: string,
  action: "submit" | "approve" | "issue" | "return",
  body: Record<string, unknown> = {},
) =>
  apiFetch<AssetIssue>(`${base}/issues/${id(issue)}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
export const registerProcurementAsset = (body: Record<string, unknown>) =>
  apiFetch<RegistrationResult>(`${base}/procurement-registrations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
export const listApprovedGoodsReceipts = () =>
  apiFetch<Page<PurchaseReceipt>>("/api/procurement/purchase-receipts", {
    query: { status: "APPROVED", receipt_type: "GOODS" },
  }).then((value) => value.results);
export const getApprovedReceipt = (value: string) =>
  apiFetch<PurchaseReceipt>(`/api/procurement/purchase-receipts/${id(value)}`);

export const listBranches = () =>
  apiFetch<Page<BranchOption> | BranchOption[]>("/api/people/branches").then(
    (value) => (Array.isArray(value) ? value : value.results),
  );
export const listEmployees = () =>
  apiFetch<Page<EmployeeOption>>("/api/people/employees", {
    query: { employment_status: "ACTIVE", ordering: "employee_number" },
  }).then((value) => value.results);
