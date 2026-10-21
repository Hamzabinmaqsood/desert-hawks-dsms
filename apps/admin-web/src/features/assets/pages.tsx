"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";

import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { FormError, FormField } from "@/components/ui/form-field";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import type { PurchaseReceipt } from "@/features/procurement/types";
import { ApiError } from "@/lib/api/client";
import {
  assetIssueAction,
  createAssetIssue,
  getApprovedReceipt,
  getAsset,
  listApprovedGoodsReceipts,
  listAssetCategories,
  listAssetIssues,
  listAssetItems,
  listAssetMovements,
  listAssets,
  listAssetStores,
  listBranches,
  listEmployees,
  registerProcurementAsset,
  updateAsset,
} from "./api";
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
} from "./types";

const selectedCompany = (auth: ReturnType<typeof useAuth>) =>
  auth.company_context.selected_company?.id ?? "";
const humanize = (value: string) => value.replaceAll("_", " ");
const errorMessage = (reason: unknown, fallback: string) =>
  reason instanceof ApiError ? reason.message : fallback;

function Status({ value }: { value: string }) {
  return (
    <span className={`status-badge status-${value.toLowerCase()}`}>
      {humanize(value)}
    </span>
  );
}

export function AssetListPage({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const auth = useAuth();
  const company = selectedCompany(auth);
  const canViewAssets = auth.can("assets.view_asset");
  const [data, setData] = useState<Page<AssetRecord> | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    if (canViewAssets)
      listAssets(searchParams)
        .then((value) => current && setData(value))
        .catch(() => current && setError("Assets could not be loaded."));
    return () => {
      current = false;
    };
  }, [canViewAssets, company, searchParams]);
  if (!canViewAssets)
    return <ErrorState message="You do not have permission to view Assets." />;
  return (
    <>
      <PageHeader
        title="Assets"
        description="Company Asset Register, custody, condition, and procurement source."
        actions={
          auth.canAny("assets.register_asset", "assets.receive_asset_stock") ? (
            <Link className="button" href="/assets/new">
              Register received Assets
            </Link>
          ) : undefined
        }
      />
      <form className="invoice-filters" action="/assets">
        <label>
          Search
          <input
            name="search"
            defaultValue={searchParams.search}
            placeholder="Asset or serial number"
          />
        </label>
        <label>
          Status
          <select name="status" defaultValue={searchParams.status}>
            <option value="">All</option>
            {[
              "AVAILABLE",
              "ISSUED",
              "UNDER_MAINTENANCE",
              "DAMAGED",
              "RETIRED",
            ].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          Condition
          <select name="condition" defaultValue={searchParams.condition}>
            <option value="">All</option>
            {[
              "NEW",
              "EXCELLENT",
              "GOOD",
              "FAIR",
              "POOR",
              "DAMAGED",
              "UNSERVICEABLE",
            ].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <Button>Filter</Button>
      </form>
      {error ? (
        <ErrorState message={error} />
      ) : !data ? (
        <LoadingState label="Loading Assets..." />
      ) : data.results.length ? (
        <>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Asset</th>
                  <th>Item</th>
                  <th>Status</th>
                  <th>Condition</th>
                  <th>Custody</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((asset) => (
                  <tr key={asset.id}>
                    <td>
                      <Link href={`/assets/${asset.id}`}>
                        {asset.asset_number}
                      </Link>
                      <small className="table-secondary">
                        {asset.serial_number || "No serial"}
                      </small>
                    </td>
                    <td>
                      {asset.item_code} - {asset.item_name}
                    </td>
                    <td>
                      <Status value={asset.status} />
                    </td>
                    <td>{humanize(asset.condition)}</td>
                    <td>
                      {asset.current_employee_name ||
                        asset.current_branch_name ||
                        asset.current_warehouse_name ||
                        humanize(asset.current_custody_type)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>{data.count} Assets</p>
        </>
      ) : (
        <EmptyState message="No Assets match this Company and filter. Register an approved goods receipt to create the Asset Register safely." />
      )}
    </>
  );
}

export function AssetRegistrationPage({
  initialReceipt = "",
}: {
  initialReceipt?: string;
}) {
  const auth = useAuth();
  const router = useRouter();
  const company = selectedCompany(auth);
  const [receipts, setReceipts] = useState<PurchaseReceipt[]>([]);
  const [receipt, setReceipt] = useState<PurchaseReceipt | null>(null);
  const [items, setItems] = useState<AssetItem[]>([]);
  const [categories, setCategories] = useState<AssetCategory[]>([]);
  const [stores, setStores] = useState<AssetStore[]>([]);
  const [values, setValues] = useState({
    receipt: initialReceipt,
    receipt_line: "",
    asset_item: "",
    destination_store: "",
    quantity: "1.000",
    serial_number: "",
  });
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    let current = true;
    Promise.all([
      listApprovedGoodsReceipts(),
      listAssetItems(),
      listAssetCategories(),
      listAssetStores(),
    ])
      .then(([receiptRows, itemRows, categoryRows, storeRows]) => {
        if (current) {
          setReceipts(receiptRows);
          setItems(itemRows);
          setCategories(categoryRows);
          setStores(storeRows);
        }
      })
      .catch(
        () =>
          current &&
          setMessage(
            "Receipt, catalog, or Store references could not be loaded.",
          ),
      );
    return () => {
      current = false;
    };
  }, [company]);
  useEffect(() => {
    if (!values.receipt) return;
    let current = true;
    getApprovedReceipt(values.receipt)
      .then((value) => current && setReceipt(value))
      .catch(
        () =>
          current && setMessage("The Purchase Receipt could not be loaded."),
      );
    return () => {
      current = false;
    };
  }, [values.receipt]);
  const selectedItem = items.find((item) => item.id === values.asset_item);
  const selectedReceipt = values.receipt ? receipt : null;
  const selectedCategory = categories.find(
    (category) => category.id === selectedItem?.category,
  );
  const serialized = selectedCategory?.tracking_method === "SERIALIZED";
  if (!auth.canAny("assets.register_asset", "assets.receive_asset_stock"))
    return (
      <ErrorState message="You do not have permission to register received Assets or stock." />
    );
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setMessage("");
    try {
      const payload: Record<string, unknown> = {
        receipt_line: values.receipt_line,
        asset_item: values.asset_item,
        destination_store: values.destination_store,
        idempotency_key: crypto.randomUUID(),
      };
      if (serialized)
        payload.assets = [
          {
            receipt_unit_key: crypto.randomUUID(),
            serial_number: values.serial_number,
          },
        ];
      else payload.quantity = values.quantity;
      const result = await registerProcurementAsset(payload);
      const assetId = result.results.find((entry) => entry.asset)?.asset;
      router.push(assetId ? `/assets/${assetId}` : "/assets");
    } catch (reason) {
      setMessage(
        errorMessage(reason, "The procurement inventory registration failed."),
      );
    } finally {
      setPending(false);
    }
  }
  return (
    <>
      <PageHeader
        title="Register received Assets"
        description="Create serialized Assets or stock only from an approved goods receipt."
      />
      <form className="invoice-form" onSubmit={submit}>
        <label className="form-field">
          <span>Approved goods receipt</span>
          <select
            required
            value={values.receipt}
            onChange={(event) =>
              setValues({
                ...values,
                receipt: event.target.value,
                receipt_line: "",
              })
            }
          >
            <option value="">Select receipt</option>
            {receipts.map((item) => (
              <option key={item.id} value={item.id}>
                {item.receipt_number} - {item.purchase_order_number}
              </option>
            ))}
          </select>
        </label>
        <label className="form-field">
          <span>Receipt line</span>
          <select
            required
            value={values.receipt_line}
            onChange={(event) =>
              setValues({ ...values, receipt_line: event.target.value })
            }
          >
            <option value="">Select received line</option>
            {selectedReceipt?.lines.map((line) => (
              <option key={line.id} value={line.id}>
                {line.description} - accepted {line.accepted_quantity}
              </option>
            ))}
          </select>
        </label>
        <label className="form-field">
          <span>Catalog item</span>
          <select
            required
            value={values.asset_item}
            onChange={(event) =>
              setValues({ ...values, asset_item: event.target.value })
            }
          >
            <option value="">Select Asset item</option>
            {items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.item_code} - {item.name}
              </option>
            ))}
          </select>
        </label>
        <label className="form-field">
          <span>Destination Store</span>
          <select
            required
            value={values.destination_store}
            onChange={(event) =>
              setValues({ ...values, destination_store: event.target.value })
            }
          >
            <option value="">Select Store</option>
            {stores.map((store) => (
              <option key={store.id} value={store.id}>
                {store.code} - {store.name}
              </option>
            ))}
          </select>
        </label>
        {serialized ? (
          <FormField
            id="serial_number"
            label="Serial number"
            required
            value={values.serial_number}
            onChange={(event) =>
              setValues({ ...values, serial_number: event.target.value })
            }
          />
        ) : (
          <FormField
            id="quantity"
            label="Quantity"
            type="number"
            required
            value={values.quantity}
            onChange={(event) =>
              setValues({ ...values, quantity: event.target.value })
            }
          />
        )}
        <FormError message={message} />
        <div className="filter-actions">
          <Button disabled={pending}>
            {pending ? "Registering..." : "Register inventory"}
          </Button>
          <Link className="button button-secondary" href="/assets">
            Cancel
          </Link>
        </div>
      </form>
    </>
  );
}

function AssetEditForm({ asset }: { asset: AssetRecord }) {
  const auth = useAuth();
  const router = useRouter();
  const [values, setValues] = useState({
    warranty_expires_on: asset.warranty_expires_on ?? "",
    expected_retirement_on: asset.expected_retirement_on ?? "",
    notes: asset.notes,
  });
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  if (!auth.can("assets.change_asset"))
    return (
      <ErrorState message="You do not have permission to edit Asset metadata." />
    );
  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    try {
      await updateAsset(asset.id, values);
      router.push(`/assets/${asset.id}`);
    } catch (reason) {
      setMessage(errorMessage(reason, "Asset metadata could not be saved."));
    } finally {
      setPending(false);
    }
  }
  return (
    <form className="invoice-form" onSubmit={submit}>
      <FormField
        id="warranty_expires_on"
        label="Warranty expires"
        type="date"
        value={values.warranty_expires_on}
        onChange={(event) =>
          setValues({ ...values, warranty_expires_on: event.target.value })
        }
      />
      <FormField
        id="expected_retirement_on"
        label="Expected retirement"
        type="date"
        value={values.expected_retirement_on}
        onChange={(event) =>
          setValues({ ...values, expected_retirement_on: event.target.value })
        }
      />
      <label className="form-field">
        <span>Notes</span>
        <textarea
          value={values.notes}
          onChange={(event) =>
            setValues({ ...values, notes: event.target.value })
          }
        />
      </label>
      <p>
        Custody, status, and condition change only through Issue, Return, and
        Movement services.
      </p>
      <FormError message={message} />
      <div className="filter-actions">
        <Button disabled={pending}>
          {pending ? "Saving..." : "Save Asset metadata"}
        </Button>
        <Link className="button button-secondary" href={`/assets/${asset.id}`}>
          Cancel
        </Link>
      </div>
    </form>
  );
}

export function AssetEditPage({ id }: { id: string }) {
  const auth = useAuth();
  const company = selectedCompany(auth);
  const [asset, setAsset] = useState<AssetRecord | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    getAsset(id)
      .then((value) => current && setAsset(value))
      .catch(
        (reason) =>
          current &&
          setError(errorMessage(reason, "Asset could not be loaded.")),
      );
    return () => {
      current = false;
    };
  }, [company, id]);
  return error ? (
    <ErrorState message={error} />
  ) : !asset ? (
    <LoadingState label="Loading Asset..." />
  ) : (
    <>
      <PageHeader
        title={`Edit ${asset.asset_number}`}
        description="Safe metadata only"
      />
      <AssetEditForm asset={asset} />
    </>
  );
}

function IssuePanel({
  asset,
  issues,
  reload,
}: {
  asset: AssetRecord;
  issues: AssetIssue[];
  reload: () => Promise<void>;
}) {
  const auth = useAuth();
  const company = selectedCompany(auth);
  const canViewEmployees =
    auth.hasModule("people") && auth.can("workforce.view_employee");
  const [branches, setBranches] = useState<BranchOption[]>([]);
  const [employees, setEmployees] = useState<EmployeeOption[]>([]);
  const [values, setValues] = useState({
    issue_number: "",
    issue_type: "LONG_TERM",
    recipient_type: "BRANCH",
    branch: "",
    employee: "",
    expected_return_at: "",
    purpose: "",
    notes: "",
  });
  const [returnValues, setReturnValues] = useState({
    return_number: "",
    return_condition: "GOOD",
    damage_notes: "",
    requires_maintenance: false,
  });
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    let current = true;
    const loaders: Promise<unknown>[] = [
      listBranches().then((value) => current && setBranches(value)),
    ];
    if (canViewEmployees)
      loaders.push(
        listEmployees().then((value) => current && setEmployees(value)),
      );
    Promise.all(loaders).catch(
      () => current && setMessage("Recipient references could not be loaded."),
    );
    return () => {
      current = false;
    };
  }, [canViewEmployees, company]);
  const open = issues.find((issue) =>
    [
      "DRAFT",
      "PENDING_APPROVAL",
      "APPROVED",
      "ISSUED",
      "PARTIALLY_RETURNED",
    ].includes(issue.status),
  );
  async function create(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setMessage("");
    try {
      await createAssetIssue({
        asset: asset.id,
        issue_number: values.issue_number,
        issue_type: values.issue_type,
        branch: values.recipient_type === "BRANCH" ? values.branch : null,
        employee: values.recipient_type === "EMPLOYEE" ? values.employee : null,
        expected_return_at: values.expected_return_at || null,
        purpose: values.purpose,
        notes: values.notes,
      });
      await reload();
    } catch (reason) {
      setMessage(errorMessage(reason, "The Asset issue request failed."));
    } finally {
      setPending(false);
    }
  }
  async function action(
    issue: AssetIssue,
    name: "submit" | "approve" | "issue",
  ) {
    setPending(true);
    setMessage("");
    try {
      await assetIssueAction(issue.id, name);
      await reload();
    } catch (reason) {
      setMessage(errorMessage(reason, "The Asset workflow action failed."));
    } finally {
      setPending(false);
    }
  }
  async function receive(event: FormEvent, issue: AssetIssue) {
    event.preventDefault();
    setPending(true);
    try {
      await assetIssueAction(issue.id, "return", {
        ...returnValues,
        returned_at: new Date().toISOString(),
      });
      await reload();
    } catch (reason) {
      setMessage(errorMessage(reason, "The Asset return failed."));
    } finally {
      setPending(false);
    }
  }
  return (
    <section className="detail-card">
      <h2>Issue / Return</h2>
      <FormError message={message} />
      {open ? (
        <article>
          <p>
            <strong>{open.issue_number}</strong> -{" "}
            <Status value={open.status} />
          </p>
          <p>
            {open.purpose} · {open.employee_name || open.branch_name}
          </p>
          {open.status === "DRAFT" && auth.can("assets.change_assetissue") ? (
            <details>
              <summary>Submit issue request</summary>
              <Button disabled={pending} onClick={() => action(open, "submit")}>
                Confirm submit
              </Button>
            </details>
          ) : null}
          {open.status === "PENDING_APPROVAL" &&
          auth.can("assets.approve_asset_issue") ? (
            <details>
              <summary>Approve issue</summary>
              <p>Maker/checker policy applies.</p>
              <Button
                disabled={pending}
                onClick={() => action(open, "approve")}
              >
                Confirm approval
              </Button>
            </details>
          ) : null}
          {open.status === "APPROVED" && auth.can("assets.issue_asset") ? (
            <details>
              <summary>Issue Asset</summary>
              <Button disabled={pending} onClick={() => action(open, "issue")}>
                Confirm issue
              </Button>
            </details>
          ) : null}
          {["ISSUED", "PARTIALLY_RETURNED"].includes(open.status) &&
          auth.can("assets.add_assetreturn") ? (
            <details>
              <summary>Receive return</summary>
              <form
                className="compact-form"
                onSubmit={(event) => receive(event, open)}
              >
                <label>
                  Return number
                  <input
                    required
                    value={returnValues.return_number}
                    onChange={(event) =>
                      setReturnValues({
                        ...returnValues,
                        return_number: event.target.value,
                      })
                    }
                  />
                </label>
                <label>
                  Condition
                  <select
                    value={returnValues.return_condition}
                    onChange={(event) =>
                      setReturnValues({
                        ...returnValues,
                        return_condition: event.target.value,
                      })
                    }
                  >
                    {["GOOD", "FAIR", "DAMAGED", "UNSERVICEABLE"].map(
                      (value) => (
                        <option key={value}>{value}</option>
                      ),
                    )}
                  </select>
                </label>
                <label>
                  Damage notes
                  <input
                    value={returnValues.damage_notes}
                    onChange={(event) =>
                      setReturnValues({
                        ...returnValues,
                        damage_notes: event.target.value,
                      })
                    }
                  />
                </label>
                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={returnValues.requires_maintenance}
                    onChange={(event) =>
                      setReturnValues({
                        ...returnValues,
                        requires_maintenance: event.target.checked,
                      })
                    }
                  />{" "}
                  Requires maintenance
                </label>
                <Button disabled={pending}>Confirm return</Button>
              </form>
            </details>
          ) : null}
        </article>
      ) : asset.status === "AVAILABLE" && auth.can("assets.add_assetissue") ? (
        <details>
          <summary>Create issue request</summary>
          <form className="compact-form" onSubmit={create}>
            <label>
              Issue number
              <input
                required
                value={values.issue_number}
                onChange={(event) =>
                  setValues({ ...values, issue_number: event.target.value })
                }
              />
            </label>
            <label>
              Recipient type
              <select
                value={values.recipient_type}
                onChange={(event) =>
                  setValues({ ...values, recipient_type: event.target.value })
                }
              >
                <option value="BRANCH">Branch</option>
                {employees.length ? (
                  <option value="EMPLOYEE">Employee</option>
                ) : null}
              </select>
            </label>
            {values.recipient_type === "EMPLOYEE" ? (
              <label>
                Employee
                <select
                  required
                  value={values.employee}
                  onChange={(event) =>
                    setValues({ ...values, employee: event.target.value })
                  }
                >
                  <option value="">Select Employee</option>
                  {employees.map((employee) => (
                    <option key={employee.id} value={employee.id}>
                      {employee.employee_number} - {employee.full_name}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <label>
                Branch
                <select
                  required
                  value={values.branch}
                  onChange={(event) =>
                    setValues({ ...values, branch: event.target.value })
                  }
                >
                  <option value="">Select Branch</option>
                  {branches.map((branch) => (
                    <option key={branch.id} value={branch.id}>
                      {branch.code} - {branch.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label>
              Purpose
              <input
                required
                value={values.purpose}
                onChange={(event) =>
                  setValues({ ...values, purpose: event.target.value })
                }
              />
            </label>
            <label>
              Expected return
              <input
                type="datetime-local"
                value={values.expected_return_at}
                onChange={(event) =>
                  setValues({
                    ...values,
                    expected_return_at: event.target.value,
                  })
                }
              />
            </label>
            <Button disabled={pending}>Create issue request</Button>
          </form>
        </details>
      ) : (
        <p>
          No issue action is available for the current state and permissions.
        </p>
      )}
    </section>
  );
}

export function AssetDetailPage({ id }: { id: string }) {
  const auth = useAuth();
  const company = selectedCompany(auth);
  const canViewMovements = auth.can("assets.view_assetmovement");
  const canViewIssues = auth.can("assets.view_assetissue");
  const [asset, setAsset] = useState<AssetRecord | null>(null);
  const [movements, setMovements] = useState<AssetMovement[]>([]);
  const [issues, setIssues] = useState<AssetIssue[]>([]);
  const [error, setError] = useState("");
  const fetchDetail = useCallback(async () => {
    const value = await getAsset(id);
    const [movementRows, issueRows] = await Promise.all([
      canViewMovements ? listAssetMovements(id) : Promise.resolve([]),
      canViewIssues ? listAssetIssues(id) : Promise.resolve([]),
    ]);
    return { value, movementRows, issueRows };
  }, [canViewIssues, canViewMovements, id]);
  const load = useCallback(async () => {
    try {
      const { value, movementRows, issueRows } = await fetchDetail();
      setAsset(value);
      setMovements(movementRows);
      setIssues(issueRows);
    } catch (reason) {
      setError(errorMessage(reason, "Asset could not be loaded."));
    }
  }, [fetchDetail]);
  useEffect(() => {
    let current = true;
    fetchDetail()
      .then(({ value, movementRows, issueRows }) => {
        if (current) {
          setAsset(value);
          setMovements(movementRows);
          setIssues(issueRows);
        }
      })
      .catch(
        (reason) =>
          current &&
          setError(errorMessage(reason, "Asset could not be loaded.")),
      );
    return () => {
      current = false;
    };
  }, [company, fetchDetail]);
  const custody = useMemo(
    () =>
      asset
        ? asset.current_employee_name ||
          asset.current_branch_name ||
          asset.current_warehouse_name ||
          humanize(asset.current_custody_type)
        : "",
    [asset],
  );
  if (error) return <ErrorState message={error} />;
  if (!asset) return <LoadingState label="Loading Asset..." />;
  return (
    <>
      <PageHeader
        title={asset.asset_number}
        description={`${asset.item_code} - ${asset.item_name}`}
        actions={
          auth.can("assets.change_asset") ? (
            <Link className="button" href={`/assets/${asset.id}/edit`}>
              Edit metadata
            </Link>
          ) : undefined
        }
      />
      <section className="detail-card">
        <h2>Overview</h2>
        <dl className="detail-grid">
          <dt>Category</dt>
          <dd>{asset.category_name}</dd>
          <dt>Serial number</dt>
          <dd>{asset.serial_number || "-"}</dd>
          <dt>Status</dt>
          <dd>
            <Status value={asset.status} />
          </dd>
          <dt>Condition</dt>
          <dd>{humanize(asset.condition)}</dd>
          <dt>Custody</dt>
          <dd>{custody}</dd>
          <dt>Procurement receipt</dt>
          <dd>{asset.procurement_receipt_reference || "-"}</dd>
          <dt>Purchase Order</dt>
          <dd>{asset.purchase_order_reference || "-"}</dd>
          {asset.acquisition_cost !== undefined ? (
            <>
              <dt>Acquisition cost</dt>
              <dd>{asset.acquisition_cost || "-"}</dd>
            </>
          ) : null}
        </dl>
      </section>
      <IssuePanel asset={asset} issues={issues} reload={load} />
      <section className="detail-card">
        <h2>Movements</h2>
        {movements.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Movement</th>
                  <th>From</th>
                  <th>To</th>
                </tr>
              </thead>
              <tbody>
                {movements.map((movement) => (
                  <tr key={movement.id}>
                    <td>{new Date(movement.moved_at).toLocaleString()}</td>
                    <td>{humanize(movement.movement_type)}</td>
                    <td>
                      {movement.from_custody_type
                        ? humanize(movement.from_custody_type)
                        : "-"}
                    </td>
                    <td>
                      {movement.to_custody_type
                        ? humanize(movement.to_custody_type)
                        : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState message="No Asset movements are visible." />
        )}
      </section>
      <section className="detail-card">
        <h2>Scope boundaries</h2>
        <p>
          Kits, requirement policies, and depreciation are not part of this
          Asset Management MVP.
        </p>
      </section>
    </>
  );
}
