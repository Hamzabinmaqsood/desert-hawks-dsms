"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { FormError, FormField } from "@/components/ui/form-field";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { ApiError } from "@/lib/api/client";
import {
  getOrder,
  getReceipt,
  getRequisition,
  listExpenseAccounts,
  listOrders,
  listProcurementVendors,
  listReceipts,
  listRequisitions,
  procurementAction,
  saveOrder,
  saveReceipt,
  saveRequisition,
} from "./api";
import type {
  ExpenseAccount,
  Page,
  PurchaseOrder,
  PurchaseReceipt,
  PurchaseRequisition,
  VendorOption,
} from "./types";

const companyId = (auth: ReturnType<typeof useAuth>) =>
  auth.company_context.selected_company?.id ?? "";
const statusLabel = (value: string) => value.replaceAll("_", " ");
const messageFor = (reason: unknown, fallback: string) =>
  reason instanceof ApiError ? reason.message : fallback;

function Status({ value }: { value: string }) {
  return (
    <span className={`status-badge status-${value.toLowerCase()}`}>
      {statusLabel(value)}
    </span>
  );
}

function PageLinks({ data, path }: { data: Page<unknown>; path: string }) {
  if (!data.previous && !data.next) return null;
  const pageFrom = (url: string) =>
    new URL(url).searchParams.get("page") ?? "1";
  return (
    <nav className="pagination" aria-label="Pagination">
      {data.previous ? (
        <Link href={`${path}?page=${pageFrom(data.previous)}`}>Previous</Link>
      ) : (
        <span />
      )}
      <span>{data.count} records</span>
      {data.next ? (
        <Link href={`${path}?page=${pageFrom(data.next)}`}>Next</Link>
      ) : (
        <span />
      )}
    </nav>
  );
}

function usePage<T>(
  loader: (query: Record<string, string>) => Promise<Page<T>>,
  query: Record<string, string>,
) {
  const auth = useAuth();
  const selected = companyId(auth);
  const [data, setData] = useState<Page<T> | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    loader(query)
      .then((value) => current && setData(value))
      .catch(() => current && setError("The workspace could not be loaded."));
    return () => {
      current = false;
    };
  }, [loader, query, selected]);
  return { data, error };
}

export function RequisitionListPage({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const auth = useAuth();
  const { data, error } = usePage(listRequisitions, searchParams);
  if (!auth.can("finance.view_purchaserequisition"))
    return (
      <ErrorState message="You do not have permission to view Purchase Requisitions." />
    );
  return (
    <>
      <PageHeader
        title="Purchase Requisitions"
        description="Request and approve Company purchasing needs."
        actions={
          auth.can("finance.add_purchaserequisition") ? (
            <Link className="button" href="/purchase-requisitions/new">
              New requisition
            </Link>
          ) : undefined
        }
      />
      <form className="invoice-filters" action="/purchase-requisitions">
        <label>
          Search
          <input
            name="search"
            defaultValue={searchParams.search}
            placeholder="Number or purpose"
          />
        </label>
        <label>
          Status
          <select name="status" defaultValue={searchParams.status}>
            <option value="">All</option>
            {["DRAFT", "SUBMITTED", "APPROVED", "REJECTED"].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <Button>Filter</Button>
      </form>
      {error ? (
        <ErrorState message={error} />
      ) : !data ? (
        <LoadingState label="Loading Purchase Requisitions..." />
      ) : data.results.length ? (
        <>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Requisition</th>
                  <th>Required</th>
                  <th>Purpose</th>
                  <th>Estimate</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <Link href={`/purchase-requisitions/${item.id}`}>
                        {item.requisition_number}
                      </Link>
                    </td>
                    <td>{item.required_date}</td>
                    <td>{item.purpose}</td>
                    <td>{item.estimated_total}</td>
                    <td>
                      <Status value={item.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <PageLinks data={data} path="/purchase-requisitions" />
        </>
      ) : (
        <EmptyState message="No Purchase Requisitions match this Company and filter." />
      )}
    </>
  );
}

type RequisitionLineForm = {
  description: string;
  quantity: string;
  estimated_unit_price: string;
  expense_account: string;
};
const blankRequisitionLine = (): RequisitionLineForm => ({
  description: "",
  quantity: "1",
  estimated_unit_price: "0.00",
  expense_account: "",
});

function RequisitionForm({ item }: { item?: PurchaseRequisition }) {
  const auth = useAuth();
  const selected = companyId(auth);
  const router = useRouter();
  const [accounts, setAccounts] = useState<ExpenseAccount[]>([]);
  const [values, setValues] = useState({
    requisition_number: item?.requisition_number ?? "",
    required_date: item?.required_date ?? "",
    purpose: item?.purpose ?? "",
  });
  const [lines, setLines] = useState<RequisitionLineForm[]>(
    item?.lines.map((line) => ({
      description: line.description,
      quantity: line.quantity,
      estimated_unit_price: line.estimated_unit_price,
      expense_account: line.expense_account,
    })) ?? [blankRequisitionLine()],
  );
  const [message, setMessage] = useState("");
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [pending, setPending] = useState(false);
  useEffect(() => {
    let current = true;
    listExpenseAccounts()
      .then((value) => current && setAccounts(value))
      .catch(
        () => current && setMessage("Expense accounts could not be loaded."),
      );
    return () => {
      current = false;
    };
  }, [selected]);
  const permission = item
    ? "finance.change_purchaserequisition"
    : "finance.add_purchaserequisition";
  if (!auth.can(permission))
    return (
      <ErrorState message="You do not have permission to manage Purchase Requisitions." />
    );
  const updateLine = (
    index: number,
    key: keyof RequisitionLineForm,
    value: string,
  ) =>
    setLines((current) =>
      current.map((line, position) =>
        position === index ? { ...line, [key]: value } : line,
      ),
    );
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setErrors({});
    setMessage("");
    try {
      const saved = await saveRequisition(item?.id ?? null, {
        ...values,
        lines,
      });
      router.push(`/purchase-requisitions/${saved.id}`);
    } catch (reason) {
      if (reason instanceof ApiError) setErrors(reason.fieldErrors);
      setMessage(
        messageFor(reason, "The Purchase Requisition could not be saved."),
      );
    } finally {
      setPending(false);
    }
  }
  return (
    <form
      className="invoice-form"
      onSubmit={submit}
      aria-label="Purchase Requisition form"
    >
      <FormField
        id="requisition_number"
        label="Requisition number"
        required
        value={values.requisition_number}
        onChange={(event) =>
          setValues({ ...values, requisition_number: event.target.value })
        }
        error={errors.requisition_number?.[0]}
      />
      <FormField
        id="required_date"
        label="Required date"
        type="date"
        required
        value={values.required_date}
        onChange={(event) =>
          setValues({ ...values, required_date: event.target.value })
        }
        error={errors.required_date?.[0]}
      />
      <label className="form-field">
        <span>Purpose</span>
        <textarea
          required
          value={values.purpose}
          onChange={(event) =>
            setValues({ ...values, purpose: event.target.value })
          }
        />
      </label>
      <fieldset>
        <legend>Requested items</legend>
        {lines.map((line, index) => (
          <div className="line-form-grid" key={index}>
            <FormField
              id={`description-${index}`}
              label="Description"
              required
              value={line.description}
              onChange={(event) =>
                updateLine(index, "description", event.target.value)
              }
            />
            <FormField
              id={`quantity-${index}`}
              label="Quantity"
              type="number"
              required
              value={line.quantity}
              onChange={(event) =>
                updateLine(index, "quantity", event.target.value)
              }
            />
            <FormField
              id={`price-${index}`}
              label="Estimated unit price"
              type="number"
              required
              value={line.estimated_unit_price}
              onChange={(event) =>
                updateLine(index, "estimated_unit_price", event.target.value)
              }
            />
            <label className="form-field">
              <span>Expense account</span>
              <select
                required
                value={line.expense_account}
                onChange={(event) =>
                  updateLine(index, "expense_account", event.target.value)
                }
              >
                <option value="">Select account</option>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.code} - {account.name}
                  </option>
                ))}
              </select>
            </label>
            {lines.length > 1 ? (
              <Button
                type="button"
                className="button-secondary"
                onClick={() =>
                  setLines((current) =>
                    current.filter((_, position) => position !== index),
                  )
                }
              >
                Remove line
              </Button>
            ) : null}
          </div>
        ))}
      </fieldset>
      <Button
        type="button"
        className="button-secondary"
        onClick={() =>
          setLines((current) => [...current, blankRequisitionLine()])
        }
      >
        Add line
      </Button>
      <FormError message={message} />
      <div className="filter-actions">
        <Button disabled={pending}>
          {pending ? "Saving..." : "Save requisition"}
        </Button>
        <Link
          className="button button-secondary"
          href={
            item
              ? `/purchase-requisitions/${item.id}`
              : "/purchase-requisitions"
          }
        >
          Cancel
        </Link>
      </div>
    </form>
  );
}

export function RequisitionCreatePage() {
  return (
    <>
      <PageHeader
        title="New Purchase Requisition"
        description="Create a draft request with explicit item estimates."
      />
      <RequisitionForm />
    </>
  );
}
export function RequisitionEditPage({ id }: { id: string }) {
  const [item, setItem] = useState<PurchaseRequisition | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    getRequisition(id)
      .then((value) => current && setItem(value))
      .catch(
        (reason) =>
          current &&
          setError(
            messageFor(reason, "Purchase Requisition could not be loaded."),
          ),
      );
    return () => {
      current = false;
    };
  }, [id]);
  return error ? (
    <ErrorState message={error} />
  ) : !item ? (
    <LoadingState label="Loading Purchase Requisition..." />
  ) : (
    <>
      <PageHeader title={`Edit ${item.requisition_number}`} />
      <RequisitionForm item={item} />
    </>
  );
}

function WorkflowActions({
  resource,
  item,
  reload,
}: {
  resource: "purchase-requisitions" | "purchase-orders";
  item: PurchaseRequisition | PurchaseOrder;
  reload: () => Promise<void>;
}) {
  const auth = useAuth();
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const run = async (action: "submit" | "approve" | "reject") => {
    setPending(true);
    setMessage("");
    try {
      await procurementAction(resource, item.id, action, reason);
      await reload();
    } catch (error) {
      setMessage(messageFor(error, "The workflow action failed."));
    } finally {
      setPending(false);
    }
  };
  const model =
    resource === "purchase-orders" ? "purchaseorder" : "purchaserequisition";
  return (
    <section className="detail-card">
      <h2>Workflow</h2>
      <FormError message={message} />
      {item.status === "DRAFT" && auth.can(`finance.change_${model}`) ? (
        <details>
          <summary>Submit for approval</summary>
          <p>Submitting locks the draft for approval.</p>
          <Button disabled={pending} onClick={() => run("submit")}>
            Confirm submit
          </Button>
        </details>
      ) : null}
      {item.status === "SUBMITTED" && auth.can("finance.approve_finance") ? (
        <>
          <details>
            <summary>Approve</summary>
            <p>Approval is subject to maker/checker policy.</p>
            <Button disabled={pending} onClick={() => run("approve")}>
              Confirm approval
            </Button>
          </details>
          <details>
            <summary>Reject</summary>
            <label>
              Reason
              <input
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </label>
            <Button
              disabled={pending || !reason.trim()}
              onClick={() => run("reject")}
            >
              Confirm rejection
            </Button>
          </details>
        </>
      ) : null}
    </section>
  );
}

export function RequisitionDetailPage({ id }: { id: string }) {
  const auth = useAuth();
  const selected = companyId(auth);
  const [item, setItem] = useState<PurchaseRequisition | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      setItem(await getRequisition(id));
    } catch (reason) {
      setError(messageFor(reason, "Purchase Requisition could not be loaded."));
    }
  }, [id]);
  useEffect(() => {
    let current = true;
    getRequisition(id)
      .then((value) => current && setItem(value))
      .catch(
        (reason) =>
          current &&
          setError(
            messageFor(reason, "Purchase Requisition could not be loaded."),
          ),
      );
    return () => {
      current = false;
    };
  }, [id, selected]);
  if (error) return <ErrorState message={error} />;
  if (!item) return <LoadingState label="Loading Purchase Requisition..." />;
  return (
    <>
      <PageHeader
        title={item.requisition_number}
        description={item.purpose}
        actions={
          item.status === "DRAFT" &&
          auth.can("finance.change_purchaserequisition") ? (
            <Link
              className="button"
              href={`/purchase-requisitions/${item.id}/edit`}
            >
              Edit
            </Link>
          ) : undefined
        }
      />
      <section className="detail-card">
        <dl className="detail-grid">
          <dt>Required date</dt>
          <dd>{item.required_date}</dd>
          <dt>Status</dt>
          <dd>
            <Status value={item.status} />
          </dd>
          <dt>Estimate</dt>
          <dd>{item.estimated_total}</dd>
          <dt>Created by</dt>
          <dd>{item.created_by_name}</dd>
        </dl>
      </section>
      <LineTable
        headings={["Description", "Quantity", "Unit estimate", "Account"]}
        rows={item.lines.map((line) => [
          line.description,
          line.quantity,
          line.estimated_unit_price,
          `${line.expense_account_code} - ${line.expense_account_name}`,
        ])}
        empty="No requisition lines."
      />
      <WorkflowActions
        resource="purchase-requisitions"
        item={item}
        reload={load}
      />
      {item.status === "APPROVED" && auth.can("finance.add_purchaseorder") ? (
        <Link
          className="button"
          href={`/purchase-orders/new?requisition=${item.id}`}
        >
          Create Purchase Order
        </Link>
      ) : null}
    </>
  );
}

function LineTable({
  headings,
  rows,
  empty,
}: {
  headings: string[];
  rows: string[][];
  empty: string;
}) {
  return (
    <section className="detail-card">
      <h2>Lines</h2>
      {rows.length ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                {headings.map((heading) => (
                  <th key={heading}>{heading}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index}>
                  {row.map((value, cell) => (
                    <td key={cell}>{value}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState message={empty} />
      )}
    </section>
  );
}

export function OrderListPage({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const auth = useAuth();
  const { data, error } = usePage(listOrders, searchParams);
  if (!auth.can("finance.view_purchaseorder"))
    return (
      <ErrorState message="You do not have permission to view Purchase Orders." />
    );
  return (
    <>
      <PageHeader
        title="Purchase Orders"
        description="Approved supplier commitments and receipt progress."
        actions={
          auth.can("finance.add_purchaseorder") ? (
            <Link className="button" href="/purchase-orders/new">
              New order
            </Link>
          ) : undefined
        }
      />
      <form className="invoice-filters" action="/purchase-orders">
        <label>
          Search
          <input name="search" defaultValue={searchParams.search} />
        </label>
        <label>
          Status
          <select name="status" defaultValue={searchParams.status}>
            <option value="">All</option>
            {["DRAFT", "SUBMITTED", "APPROVED", "REJECTED"].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <Button>Filter</Button>
      </form>
      {error ? (
        <ErrorState message={error} />
      ) : !data ? (
        <LoadingState label="Loading Purchase Orders..." />
      ) : data.results.length ? (
        <>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Vendor</th>
                  <th>Requisition</th>
                  <th>Total</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <Link href={`/purchase-orders/${item.id}`}>
                        {item.order_number}
                      </Link>
                    </td>
                    <td>{item.vendor_name}</td>
                    <td>{item.requisition_number}</td>
                    <td>{item.total_amount}</td>
                    <td>
                      <Status value={item.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <PageLinks data={data} path="/purchase-orders" />
        </>
      ) : (
        <EmptyState message="No Purchase Orders match this Company and filter." />
      )}
    </>
  );
}

type OrderLineForm = {
  requisition_line: string;
  description: string;
  quantity: string;
  unit_price: string;
  tax_amount: string;
};
function OrderForm({
  item,
  initialRequisition = "",
}: {
  item?: PurchaseOrder;
  initialRequisition?: string;
}) {
  const auth = useAuth();
  const selected = companyId(auth);
  const router = useRouter();
  const [requisitions, setRequisitions] = useState<PurchaseRequisition[]>([]);
  const [vendors, setVendors] = useState<VendorOption[]>([]);
  const [requisition, setRequisition] = useState<PurchaseRequisition | null>(
    null,
  );
  const [values, setValues] = useState({
    requisition: item?.requisition ?? initialRequisition,
    vendor: item?.vendor ?? "",
    order_number: item?.order_number ?? "",
    order_date: item?.order_date ?? "",
  });
  const [lines, setLines] = useState<OrderLineForm[]>(
    item?.lines.map((line) => ({
      requisition_line: line.requisition_line,
      description: line.description,
      quantity: line.quantity,
      unit_price: line.unit_price,
      tax_amount: line.tax_amount,
    })) ?? [],
  );
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    let current = true;
    Promise.all([
      listRequisitions({ status: "APPROVED" }),
      listProcurementVendors(),
    ])
      .then(([page, options]) => {
        if (current) {
          setRequisitions(page.results);
          setVendors(options);
        }
      })
      .catch(
        () =>
          current &&
          setMessage("Approved Requisitions or Vendors could not be loaded."),
      );
    return () => {
      current = false;
    };
  }, [selected]);
  useEffect(() => {
    if (!values.requisition) return;
    getRequisition(values.requisition)
      .then((source) => {
        setRequisition(source);
        if (!item)
          setLines(
            source.lines.map((line) => ({
              requisition_line: line.id,
              description: line.description,
              quantity: line.quantity,
              unit_price: line.estimated_unit_price,
              tax_amount: "0.00",
            })),
          );
      })
      .catch(() => setMessage("The selected Requisition could not be loaded."));
  }, [item, values.requisition]);
  if (
    !auth.can(
      item ? "finance.change_purchaseorder" : "finance.add_purchaseorder",
    )
  )
    return (
      <ErrorState message="You do not have permission to manage Purchase Orders." />
    );
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setMessage("");
    try {
      const saved = await saveOrder(item?.id ?? null, { ...values, lines });
      router.push(`/purchase-orders/${saved.id}`);
    } catch (reason) {
      setMessage(messageFor(reason, "The Purchase Order could not be saved."));
    } finally {
      setPending(false);
    }
  }
  const setLine = (index: number, key: keyof OrderLineForm, value: string) =>
    setLines((current) =>
      current.map((line, position) =>
        position === index ? { ...line, [key]: value } : line,
      ),
    );
  return (
    <form className="invoice-form" onSubmit={submit}>
      <label className="form-field">
        <span>Approved requisition</span>
        <select
          required
          value={values.requisition}
          onChange={(event) =>
            setValues({ ...values, requisition: event.target.value })
          }
        >
          <option value="">Select requisition</option>
          {requisitions.map((option) => (
            <option key={option.id} value={option.id}>
              {option.requisition_number} - {option.purpose}
            </option>
          ))}
        </select>
      </label>
      <label className="form-field">
        <span>Vendor</span>
        <select
          required
          value={values.vendor}
          onChange={(event) =>
            setValues({ ...values, vendor: event.target.value })
          }
        >
          <option value="">Select Vendor</option>
          {vendors.map((vendor) => (
            <option key={vendor.id} value={vendor.id}>
              {vendor.code} - {vendor.name}
            </option>
          ))}
        </select>
      </label>
      <FormField
        id="order_number"
        label="Order number"
        required
        value={values.order_number}
        onChange={(event) =>
          setValues({ ...values, order_number: event.target.value })
        }
      />
      <FormField
        id="order_date"
        label="Order date"
        type="date"
        required
        value={values.order_date}
        onChange={(event) =>
          setValues({ ...values, order_date: event.target.value })
        }
      />
      <fieldset>
        <legend>Order lines</legend>
        {lines.map((line, index) => (
          <div className="line-form-grid" key={line.requisition_line}>
            <span>{line.description}</span>
            <FormField
              id={`order-quantity-${index}`}
              label="Quantity"
              type="number"
              value={line.quantity}
              onChange={(event) =>
                setLine(index, "quantity", event.target.value)
              }
            />
            <FormField
              id={`unit-price-${index}`}
              label="Unit price"
              type="number"
              value={line.unit_price}
              onChange={(event) =>
                setLine(index, "unit_price", event.target.value)
              }
            />
            <FormField
              id={`tax-${index}`}
              label="Tax"
              type="number"
              value={line.tax_amount}
              onChange={(event) =>
                setLine(index, "tax_amount", event.target.value)
              }
            />
          </div>
        ))}
      </fieldset>
      {requisition && !lines.length ? (
        <EmptyState message="The Requisition has no orderable lines." />
      ) : null}
      <FormError message={message} />
      <div className="filter-actions">
        <Button disabled={pending || !lines.length}>
          {pending ? "Saving..." : "Save Purchase Order"}
        </Button>
        <Link
          className="button button-secondary"
          href={item ? `/purchase-orders/${item.id}` : "/purchase-orders"}
        >
          Cancel
        </Link>
      </div>
    </form>
  );
}
export function OrderCreatePage({
  requisition = "",
}: {
  requisition?: string;
}) {
  return (
    <>
      <PageHeader
        title="New Purchase Order"
        description="Create an order from an approved Purchase Requisition."
      />
      <OrderForm initialRequisition={requisition} />
    </>
  );
}
export function OrderEditPage({ id }: { id: string }) {
  const [item, setItem] = useState<PurchaseOrder | null>(null);
  useEffect(() => {
    getOrder(id).then(setItem);
  }, [id]);
  return !item ? (
    <LoadingState label="Loading Purchase Order..." />
  ) : (
    <>
      <PageHeader title={`Edit ${item.order_number}`} />
      <OrderForm item={item} />
    </>
  );
}
export function OrderDetailPage({ id }: { id: string }) {
  const auth = useAuth();
  const selected = companyId(auth);
  const [item, setItem] = useState<PurchaseOrder | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      setItem(await getOrder(id));
    } catch (reason) {
      setError(messageFor(reason, "Purchase Order could not be loaded."));
    }
  }, [id]);
  useEffect(() => {
    let current = true;
    getOrder(id)
      .then((value) => current && setItem(value))
      .catch(
        (reason) =>
          current &&
          setError(messageFor(reason, "Purchase Order could not be loaded.")),
      );
    return () => {
      current = false;
    };
  }, [id, selected]);
  if (error) return <ErrorState message={error} />;
  if (!item) return <LoadingState label="Loading Purchase Order..." />;
  return (
    <>
      <PageHeader
        title={item.order_number}
        description={`${item.vendor_code} - ${item.vendor_name}`}
        actions={
          item.status === "DRAFT" &&
          auth.can("finance.change_purchaseorder") ? (
            <Link className="button" href={`/purchase-orders/${item.id}/edit`}>
              Edit
            </Link>
          ) : undefined
        }
      />
      <section className="detail-card">
        <dl className="detail-grid">
          <dt>Requisition</dt>
          <dd>
            <Link href={`/purchase-requisitions/${item.requisition}`}>
              {item.requisition_number}
            </Link>
          </dd>
          <dt>Order date</dt>
          <dd>{item.order_date}</dd>
          <dt>Total</dt>
          <dd>{item.total_amount}</dd>
          <dt>Status</dt>
          <dd>
            <Status value={item.status} />
          </dd>
        </dl>
      </section>
      <LineTable
        headings={["Description", "Ordered", "Received", "Unit price", "Total"]}
        rows={item.lines.map((line) => [
          line.description,
          line.quantity,
          line.received_quantity,
          line.unit_price,
          line.line_total,
        ])}
        empty="No Purchase Order lines."
      />
      <WorkflowActions resource="purchase-orders" item={item} reload={load} />
      {item.status === "APPROVED" && auth.can("finance.add_purchasereceipt") ? (
        <Link
          className="button"
          href={`/purchase-receipts/new?purchase_order=${item.id}`}
        >
          Record receipt
        </Link>
      ) : null}
    </>
  );
}

export function ReceiptListPage({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const auth = useAuth();
  const { data, error } = usePage(listReceipts, searchParams);
  if (!auth.can("finance.view_purchasereceipt"))
    return (
      <ErrorState message="You do not have permission to view Purchase Receipts." />
    );
  return (
    <>
      <PageHeader
        title="Purchase Receipts"
        description="Record partial or complete receipt against approved Purchase Orders."
        actions={
          auth.can("finance.add_purchasereceipt") ? (
            <Link className="button" href="/purchase-receipts/new">
              New receipt
            </Link>
          ) : undefined
        }
      />
      <form className="invoice-filters" action="/purchase-receipts">
        <label>
          Search
          <input name="search" defaultValue={searchParams.search} />
        </label>
        <label>
          Status
          <select name="status" defaultValue={searchParams.status}>
            <option value="">All</option>
            <option>DRAFT</option>
            <option>APPROVED</option>
          </select>
        </label>
        <Button>Filter</Button>
      </form>
      {error ? (
        <ErrorState message={error} />
      ) : !data ? (
        <LoadingState label="Loading Purchase Receipts..." />
      ) : data.results.length ? (
        <>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Receipt</th>
                  <th>Purchase Order</th>
                  <th>Vendor</th>
                  <th>Date</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <Link href={`/purchase-receipts/${item.id}`}>
                        {item.receipt_number}
                      </Link>
                    </td>
                    <td>{item.purchase_order_number}</td>
                    <td>{item.vendor_name}</td>
                    <td>{item.receipt_date}</td>
                    <td>
                      <Status value={item.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <PageLinks data={data} path="/purchase-receipts" />
        </>
      ) : (
        <EmptyState message="No Purchase Receipts match this Company and filter." />
      )}
    </>
  );
}

type ReceiptLineForm = {
  purchase_order_line: string;
  description: string;
  quantity: string;
  accepted_quantity: string;
  notes: string;
};
function ReceiptForm({
  item,
  initialOrder = "",
}: {
  item?: PurchaseReceipt;
  initialOrder?: string;
}) {
  const auth = useAuth();
  const selected = companyId(auth);
  const router = useRouter();
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [values, setValues] = useState({
    purchase_order: item?.purchase_order ?? initialOrder,
    receipt_number: item?.receipt_number ?? "",
    receipt_date: item?.receipt_date ?? "",
    receipt_type: item?.receipt_type ?? "GOODS",
  });
  const [lines, setLines] = useState<ReceiptLineForm[]>(
    item?.lines.map((line) => ({
      purchase_order_line: line.purchase_order_line,
      description: line.description,
      quantity: line.quantity,
      accepted_quantity: line.accepted_quantity,
      notes: line.notes,
    })) ?? [],
  );
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const selectedOrderReady =
    Boolean(item) || orders.some((order) => order.id === values.purchase_order);
  useEffect(() => {
    let current = true;
    listOrders({ status: "APPROVED" })
      .then((page) => current && setOrders(page.results))
      .catch(
        () =>
          current &&
          setMessage("Approved Purchase Orders could not be loaded."),
      );
    return () => {
      current = false;
    };
  }, [selected]);
  useEffect(() => {
    if (!values.purchase_order || item) return;
    getOrder(values.purchase_order)
      .then((order) =>
        setLines(
          order.lines
            .filter(
              (line) => Number(line.received_quantity) < Number(line.quantity),
            )
            .map((line) => {
              const remaining = String(
                Number(line.quantity) - Number(line.received_quantity),
              );
              return {
                purchase_order_line: line.id,
                description: line.description,
                quantity: remaining,
                accepted_quantity: remaining,
                notes: "",
              };
            }),
        ),
      )
      .catch(() =>
        setMessage("The selected Purchase Order could not be loaded."),
      );
  }, [item, values.purchase_order]);
  if (
    !auth.can(
      item ? "finance.change_purchasereceipt" : "finance.add_purchasereceipt",
    )
  )
    return (
      <ErrorState message="You do not have permission to manage Purchase Receipts." />
    );
  const setLine = (index: number, key: keyof ReceiptLineForm, value: string) =>
    setLines((current) =>
      current.map((line, position) =>
        position === index ? { ...line, [key]: value } : line,
      ),
    );
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setMessage("");
    try {
      const saved = await saveReceipt(item?.id ?? null, {
        ...values,
        lines: lines.map((line) => ({
          purchase_order_line: line.purchase_order_line,
          quantity: line.quantity,
          accepted_quantity: line.accepted_quantity,
          notes: line.notes,
        })),
      });
      router.push(`/purchase-receipts/${saved.id}`);
    } catch (reason) {
      setMessage(
        messageFor(reason, "The Purchase Receipt could not be saved."),
      );
    } finally {
      setPending(false);
    }
  }
  return (
    <form className="invoice-form" onSubmit={submit}>
      <label className="form-field">
        <span>Approved Purchase Order</span>
        <select
          required
          value={values.purchase_order}
          onChange={(event) =>
            setValues({ ...values, purchase_order: event.target.value })
          }
        >
          <option value="">Select order</option>
          {orders.map((order) => (
            <option key={order.id} value={order.id}>
              {order.order_number} - {order.vendor_name}
            </option>
          ))}
        </select>
      </label>
      <FormField
        id="receipt_number"
        label="Receipt number"
        required
        value={values.receipt_number}
        onChange={(event) =>
          setValues({ ...values, receipt_number: event.target.value })
        }
      />
      <FormField
        id="receipt_date"
        label="Receipt date"
        type="date"
        required
        value={values.receipt_date}
        onChange={(event) =>
          setValues({ ...values, receipt_date: event.target.value })
        }
      />
      <label className="form-field">
        <span>Receipt type</span>
        <select
          value={values.receipt_type}
          onChange={(event) =>
            setValues({
              ...values,
              receipt_type: event.target.value as "GOODS" | "SERVICE",
            })
          }
        >
          <option value="GOODS">Goods</option>
          <option value="SERVICE">Service</option>
        </select>
      </label>
      <fieldset>
        <legend>Received lines</legend>
        {lines.map((line, index) => (
          <div className="line-form-grid" key={line.purchase_order_line}>
            <strong>{line.description}</strong>
            <FormField
              id={`received-${index}`}
              label="Received quantity"
              type="number"
              value={line.quantity}
              onChange={(event) =>
                setLine(index, "quantity", event.target.value)
              }
            />
            <FormField
              id={`accepted-${index}`}
              label="Accepted quantity"
              type="number"
              value={line.accepted_quantity}
              onChange={(event) =>
                setLine(index, "accepted_quantity", event.target.value)
              }
            />
            <FormField
              id={`receipt-notes-${index}`}
              label="Notes"
              value={line.notes}
              onChange={(event) => setLine(index, "notes", event.target.value)}
            />
          </div>
        ))}
      </fieldset>
      <FormError message={message} />
      <div className="filter-actions">
        <Button disabled={pending || !selectedOrderReady || !lines.length}>
          {pending ? "Saving..." : "Save Purchase Receipt"}
        </Button>
        <Link
          className="button button-secondary"
          href={item ? `/purchase-receipts/${item.id}` : "/purchase-receipts"}
        >
          Cancel
        </Link>
      </div>
    </form>
  );
}
export function ReceiptCreatePage({
  purchaseOrder = "",
}: {
  purchaseOrder?: string;
}) {
  return (
    <>
      <PageHeader
        title="New Purchase Receipt"
        description="Receive approved Purchase Order quantities; the server enforces over-receipt limits."
      />
      <ReceiptForm initialOrder={purchaseOrder} />
    </>
  );
}
export function ReceiptEditPage({ id }: { id: string }) {
  const [item, setItem] = useState<PurchaseReceipt | null>(null);
  useEffect(() => {
    getReceipt(id).then(setItem);
  }, [id]);
  return !item ? (
    <LoadingState label="Loading Purchase Receipt..." />
  ) : (
    <>
      <PageHeader title={`Edit ${item.receipt_number}`} />
      <ReceiptForm item={item} />
    </>
  );
}
export function ReceiptDetailPage({ id }: { id: string }) {
  const auth = useAuth();
  const selected = companyId(auth);
  const [item, setItem] = useState<PurchaseReceipt | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const load = useCallback(async () => {
    try {
      setItem(await getReceipt(id));
    } catch (reason) {
      setError(messageFor(reason, "Purchase Receipt could not be loaded."));
    }
  }, [id]);
  useEffect(() => {
    let current = true;
    getReceipt(id)
      .then((value) => current && setItem(value))
      .catch(
        (reason) =>
          current &&
          setError(messageFor(reason, "Purchase Receipt could not be loaded.")),
      );
    return () => {
      current = false;
    };
  }, [id, selected]);
  if (error) return <ErrorState message={error} />;
  if (!item) return <LoadingState label="Loading Purchase Receipt..." />;
  const confirm = async () => {
    setPending(true);
    try {
      await procurementAction<PurchaseReceipt>(
        "purchase-receipts",
        item.id,
        "confirm",
      );
      await load();
    } catch (reason) {
      setError(messageFor(reason, "Purchase Receipt could not be confirmed."));
    } finally {
      setPending(false);
    }
  };
  return (
    <>
      <PageHeader
        title={item.receipt_number}
        description={`${item.purchase_order_number} - ${item.vendor_name}`}
        actions={
          item.status === "DRAFT" &&
          auth.can("finance.change_purchasereceipt") ? (
            <Link
              className="button"
              href={`/purchase-receipts/${item.id}/edit`}
            >
              Edit
            </Link>
          ) : undefined
        }
      />
      <section className="detail-card">
        <dl className="detail-grid">
          <dt>Receipt date</dt>
          <dd>{item.receipt_date}</dd>
          <dt>Type</dt>
          <dd>{statusLabel(item.receipt_type)}</dd>
          <dt>Status</dt>
          <dd>
            <Status value={item.status} />
          </dd>
          <dt>Purchase Order</dt>
          <dd>
            <Link href={`/purchase-orders/${item.purchase_order}`}>
              {item.purchase_order_number}
            </Link>
          </dd>
        </dl>
      </section>
      <LineTable
        headings={["Description", "Ordered", "Received", "Accepted", "Notes"]}
        rows={item.lines.map((line) => [
          line.description,
          line.ordered_quantity,
          line.quantity,
          line.accepted_quantity,
          line.notes || "-",
        ])}
        empty="No Purchase Receipt lines."
      />
      {item.status === "DRAFT" && auth.can("finance.change_purchasereceipt") ? (
        <details className="detail-card">
          <summary>Confirm receipt</summary>
          <p>
            Confirmation records accepted quantities and prevents later draft
            editing.
          </p>
          <Button disabled={pending} onClick={confirm}>
            Confirm receipt
          </Button>
        </details>
      ) : null}
      {item.status === "APPROVED" &&
      item.receipt_type === "GOODS" &&
      auth.hasModule("asset_management") ? (
        <Link className="button" href={`/assets/new?receipt=${item.id}`}>
          Register received Assets
        </Link>
      ) : null}
      <p>
        <Link href={`/vendor-bills/new?purchase_order=${item.purchase_order}`}>
          Continue to Vendor Bills
        </Link>
      </p>
    </>
  );
}
