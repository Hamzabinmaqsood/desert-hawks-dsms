"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { FormError, FormField } from "@/components/ui/form-field";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { ApiError } from "@/lib/api/client";
import {
  addVendorBillLine,
  createVendorBill,
  deleteVendorBillLine,
  getVendorBill,
  listBillVendors,
  listExpenseAccounts,
  listVendorBills,
  updateVendorBill,
  updateVendorBillLine,
} from "./api";
import type {
  AccountOption,
  VendorBill,
  VendorBillLine,
  VendorOption,
} from "./types";
import {
  VendorBillDocuments,
  VendorBillWorkflow,
} from "./workflow-and-documents";

const statusLabel = (value: string) => value.replaceAll("_", " ");
const blankHeader = {
  vendor: "",
  bill_number: "",
  vendor_invoice_number: "",
  bill_date: "",
  due_date: "",
  match_type: "TWO_WAY",
};

function HeaderForm({ bill }: { bill?: VendorBill }) {
  const auth = useAuth();
  const router = useRouter();
  const [vendors, setVendors] = useState<VendorOption[]>([]);
  const [values, setValues] = useState({
    ...blankHeader,
    ...(bill
      ? {
          vendor: bill.vendor,
          bill_number: bill.bill_number,
          vendor_invoice_number: bill.vendor_invoice_number,
          bill_date: bill.bill_date,
          due_date: bill.due_date,
          match_type: bill.match_type ?? "TWO_WAY",
        }
      : {}),
  });
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    listBillVendors()
      .then(setVendors)
      .catch(() => setMessage("Vendors could not be loaded."));
  }, []);
  const permission = bill
    ? "finance.change_vendorbill"
    : "finance.add_vendorbill";
  if (!auth.can(permission))
    return (
      <ErrorState message="You do not have permission to manage Vendor Bills." />
    );
  const set = (key: keyof typeof blankHeader, value: string) =>
    setValues((current) => ({ ...current, [key]: value }));
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    if (values.due_date < values.bill_date) {
      setErrors({ due_date: ["Due date cannot be before the Bill date."] });
      return;
    }
    setPending(true);
    setErrors({});
    setMessage("");
    try {
      const saved = bill
        ? await updateVendorBill(bill.id, values)
        : await createVendorBill(values);
      router.push(
        bill ? `/vendor-bills/${saved.id}` : `/vendor-bills/${saved.id}/edit`,
      );
    } catch (reason) {
      if (reason instanceof ApiError) {
        setErrors(reason.fieldErrors);
        setMessage(reason.message);
      } else setMessage("The Vendor Bill could not be saved.");
    } finally {
      setPending(false);
    }
  }
  return (
    <form
      className="invoice-form"
      onSubmit={submit}
      aria-label={bill ? "Edit Vendor Bill" : "New Vendor Bill"}
    >
      <label className="form-field">
        <span>Vendor</span>
        <select
          required
          value={values.vendor}
          disabled={pending}
          onChange={(e) => set("vendor", e.target.value)}
        >
          <option value="">Select a Vendor</option>
          {vendors.map((v) => (
            <option key={v.id} value={v.id}>
              {v.code} — {v.name}
            </option>
          ))}
        </select>
        {errors.vendor?.[0] ? (
          <span className="field-error">{errors.vendor[0]}</span>
        ) : null}
      </label>
      <FormField
        id="bill_number"
        label="Internal Bill Reference"
        required
        value={values.bill_number}
        disabled={pending}
        onChange={(e) => set("bill_number", e.target.value)}
        error={errors.bill_number?.[0]}
      />
      <FormField
        id="vendor_invoice_number"
        label="Supplier Invoice Number"
        required
        value={values.vendor_invoice_number}
        disabled={pending}
        onChange={(e) => set("vendor_invoice_number", e.target.value)}
        error={errors.vendor_invoice_number?.[0]}
      />
      <FormField
        id="bill_date"
        label="Bill date"
        type="date"
        required
        value={values.bill_date}
        disabled={pending}
        onChange={(e) => set("bill_date", e.target.value)}
        error={errors.bill_date?.[0]}
      />
      <FormField
        id="due_date"
        label="Due date"
        type="date"
        required
        value={values.due_date}
        disabled={pending}
        onChange={(e) => set("due_date", e.target.value)}
        error={errors.due_date?.[0]}
      />
      <label className="form-field">
        <span>Match type</span>
        <select
          value={values.match_type}
          disabled={pending}
          onChange={(e) => set("match_type", e.target.value)}
        >
          <option value="TWO_WAY">Two-way</option>
          <option value="THREE_WAY">Three-way</option>
        </select>
        {errors.match_type?.[0] ? (
          <span className="field-error">{errors.match_type[0]}</span>
        ) : null}
      </label>
      <FormError message={message} />
      <div className="filter-actions">
        <Button disabled={pending}>
          {pending ? "Saving…" : bill ? "Save header" : "Create draft"}
        </Button>
        <Link
          className="button button-secondary"
          href={bill ? `/vendor-bills/${bill.id}` : "/vendor-bills"}
        >
          Cancel
        </Link>
      </div>
    </form>
  );
}

function Totals({ bill }: { bill: VendorBill }) {
  return (
    <dl className="invoice-totals">
      <div>
        <dt>Subtotal</dt>
        <dd>{bill.subtotal ?? "0.00"}</dd>
      </div>
      <div>
        <dt>Tax</dt>
        <dd>{bill.tax_amount ?? "0.00"}</dd>
      </div>
      <div>
        <dt>Total</dt>
        <dd>{bill.total_amount}</dd>
      </div>
      <div>
        <dt>Paid</dt>
        <dd>{bill.paid_amount}</dd>
      </div>
      <div>
        <dt>Outstanding</dt>
        <dd>{bill.outstanding_amount}</dd>
      </div>
    </dl>
  );
}

function Lines({
  bill,
  refresh,
}: {
  bill: VendorBill;
  refresh: () => Promise<void>;
}) {
  const auth = useAuth();
  const empty = {
    description: "",
    quantity: "",
    unit_price: "",
    tax_amount: "0.00",
    expense_account: "",
  };
  const [form, setForm] = useState(empty);
  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [message, setMessage] = useState("");
  useEffect(() => {
    listExpenseAccounts()
      .then(setAccounts)
      .catch(() => setMessage("Expense accounts could not be loaded."));
  }, []);
  const set = (key: keyof typeof empty, value: string) =>
    setForm((current) => ({ ...current, [key]: value }));
  const edit = (line: VendorBillLine) => {
    setEditing(line.id);
    setForm({
      description: line.description,
      quantity: line.quantity,
      unit_price: line.unit_price,
      tax_amount: line.tax_amount,
      expense_account: line.expense_account,
    });
  };
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setErrors({});
    setMessage("");
    try {
      if (editing) await updateVendorBillLine(bill.id, editing, form);
      else await addVendorBillLine(bill.id, form);
      await refresh();
      setEditing(null);
      setForm(empty);
    } catch (reason) {
      if (reason instanceof ApiError) {
        setErrors(reason.fieldErrors);
        setMessage(reason.message);
      } else setMessage("The line could not be saved.");
    } finally {
      setPending(false);
    }
  }
  async function remove(id: string) {
    if (!window.confirm("Remove this Vendor Bill line?")) return;
    setPending(true);
    try {
      await deleteVendorBillLine(bill.id, id);
      await refresh();
    } catch (reason) {
      setMessage(
        reason instanceof ApiError
          ? reason.message
          : "The line could not be removed.",
      );
    } finally {
      setPending(false);
    }
  }
  return (
    <div className="line-editor">
      {bill.lines?.length ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Description</th>
                <th>Quantity</th>
                <th>Unit price</th>
                <th>Tax</th>
                <th>Account</th>
                <th>Line total</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {bill.lines.map((line) => (
                <tr key={line.id}>
                  <td>{line.description}</td>
                  <td>{line.quantity}</td>
                  <td>{line.unit_price}</td>
                  <td>{line.tax_amount}</td>
                  <td>
                    {line.expense_account_code} — {line.expense_account_name}
                  </td>
                  <td>{line.line_total}</td>
                  <td className="filter-actions">
                    {auth.can("finance.change_vendorbillline") ? (
                      <Button
                        type="button"
                        className="button-secondary"
                        disabled={pending}
                        onClick={() => edit(line)}
                      >
                        Edit
                      </Button>
                    ) : null}
                    {auth.can("finance.delete_vendorbillline") ? (
                      <Button
                        type="button"
                        className="button-secondary"
                        disabled={pending}
                        onClick={() => void remove(line.id)}
                      >
                        Delete
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>No line items yet.</p>
      )}
      {auth.can("finance.add_vendorbillline") || editing ? (
        <form
          className="invoice-form line-form"
          onSubmit={submit}
          aria-label={
            editing ? "Edit Vendor Bill line" : "Add Vendor Bill line"
          }
        >
          <h3>{editing ? "Edit line" : "Add line"}</h3>
          <FormField
            id="line-description"
            label="Description"
            required
            value={form.description}
            disabled={pending}
            onChange={(e) => set("description", e.target.value)}
            error={errors.description?.[0]}
          />
          <FormField
            id="line-quantity"
            label="Quantity"
            required
            inputMode="decimal"
            value={form.quantity}
            disabled={pending}
            onChange={(e) => set("quantity", e.target.value)}
            error={errors.quantity?.[0]}
          />
          <FormField
            id="line-unit-price"
            label="Unit price"
            required
            inputMode="decimal"
            value={form.unit_price}
            disabled={pending}
            onChange={(e) => set("unit_price", e.target.value)}
            error={errors.unit_price?.[0]}
          />
          <FormField
            id="line-tax"
            label="Tax amount"
            required
            inputMode="decimal"
            value={form.tax_amount}
            disabled={pending}
            onChange={(e) => set("tax_amount", e.target.value)}
            error={errors.tax_amount?.[0]}
          />
          <label className="form-field">
            <span>Expense / asset account</span>
            <select
              required
              value={form.expense_account}
              disabled={pending}
              onChange={(e) => set("expense_account", e.target.value)}
            >
              <option value="">Select an account</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.code} — {a.name} ({a.account_type})
                </option>
              ))}
            </select>
            {errors.expense_account?.[0] ? (
              <span className="field-error">{errors.expense_account[0]}</span>
            ) : null}
          </label>
          <FormError message={message} />
          <div className="filter-actions">
            <Button disabled={pending}>
              {pending ? "Saving…" : editing ? "Save line" : "Add line"}
            </Button>
            {editing ? (
              <Button
                type="button"
                className="button-secondary"
                onClick={() => {
                  setEditing(null);
                  setForm(empty);
                }}
              >
                Cancel
              </Button>
            ) : null}
          </div>
        </form>
      ) : null}
    </div>
  );
}

export function VendorBillListPage({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const auth = useAuth();
  const allowed = auth.can("finance.view_vendorbill");
  const [data, setData] = useState<Awaited<
    ReturnType<typeof listVendorBills>
  > | null>(null);
  const [vendors, setVendors] = useState<VendorOption[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    if (allowed) {
      listVendorBills(searchParams)
        .then(setData)
        .catch((e) =>
          setError(
            e instanceof ApiError && e.status === 401
              ? "Your session has expired."
              : e instanceof ApiError && e.status === 403
                ? "You do not have access to Vendor Bills."
                : "Vendor Bills could not be loaded.",
          ),
        );
      listBillVendors()
        .then(setVendors)
        .catch(() => undefined);
    }
  }, [allowed, searchParams]);
  if (!allowed)
    return (
      <ErrorState message="You do not have permission to view Vendor Bills." />
    );
  const query = new URLSearchParams(searchParams);
  const page = Number(searchParams.page) || 1;
  return (
    <>
      <PageHeader
        title="Vendor Bills"
        description="Author and review supplier Bills."
        actions={
          auth.can("finance.add_vendorbill") ? (
            <Link className="button" href="/vendor-bills/new">
              New Vendor Bill
            </Link>
          ) : undefined
        }
      />
      <form className="invoice-filters" action="/vendor-bills">
        <label>
          Search
          <input
            name="search"
            defaultValue={searchParams.search}
            placeholder="Bill, supplier invoice or Vendor"
          />
        </label>
        <label>
          Status
          <select name="status" defaultValue={searchParams.status}>
            <option value="">All</option>
            {[
              "DRAFT",
              "SUBMITTED",
              "APPROVED",
              "REJECTED",
              "POSTED",
              "PARTIALLY_PAID",
              "PAID",
              "CLOSED",
              "CANCELLED",
            ].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label>
          Vendor
          <select name="vendor" defaultValue={searchParams.vendor}>
            <option value="">All</option>
            {vendors.map((v) => (
              <option key={v.id} value={v.id}>
                {v.code} — {v.name}
              </option>
            ))}
          </select>
        </label>
        <div className="filter-actions">
          <Button>Apply</Button>
          <Link className="button button-secondary" href="/vendor-bills">
            Clear
          </Link>
        </div>
      </form>
      {error ? (
        <ErrorState message={error} />
      ) : !data ? (
        <LoadingState label="Loading Vendor Bills…" />
      ) : !data.results.length ? (
        <EmptyState
          message={
            query.size
              ? "No Vendor Bills match these filters."
              : "No Vendor Bills found."
          }
        />
      ) : (
        <>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Bill #</th>
                  <th>Supplier Invoice #</th>
                  <th>Vendor</th>
                  <th>Bill date</th>
                  <th>Due date</th>
                  <th>Status</th>
                  <th>Total</th>
                  <th>Paid</th>
                  <th>Outstanding</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((b) => (
                  <tr key={b.id}>
                    <td>
                      <Link href={`/vendor-bills/${b.id}`}>
                        {b.bill_number}
                      </Link>
                    </td>
                    <td>{b.vendor_invoice_number}</td>
                    <td>
                      {b.vendor_code} — {b.vendor_name}
                    </td>
                    <td>{b.bill_date}</td>
                    <td>{b.due_date}</td>
                    <td>{statusLabel(b.status)}</td>
                    <td>{b.total_amount}</td>
                    <td>{b.paid_amount}</td>
                    <td>{b.outstanding_amount}</td>
                    <td>
                      {b.status === "DRAFT" &&
                      auth.can("finance.change_vendorbill") ? (
                        <Link href={`/vendor-bills/${b.id}/edit`}>Edit</Link>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="filter-actions">
            {data.previous ? (
              <Link
                className="button button-secondary"
                href={`?${new URLSearchParams({ ...searchParams, page: String(page - 1) })}`}
              >
                Previous
              </Link>
            ) : null}
            <span>Page {page}</span>
            {data.next ? (
              <Link
                className="button button-secondary"
                href={`?${new URLSearchParams({ ...searchParams, page: String(page + 1) })}`}
              >
                Next
              </Link>
            ) : null}
          </div>
        </>
      )}
    </>
  );
}

export function VendorBillCreatePage() {
  return (
    <>
      <PageHeader
        title="New Vendor Bill"
        description="Create a draft supplier Bill."
      />
      <HeaderForm />
    </>
  );
}

function useBill(id: string, allowed: boolean) {
  const [bill, setBill] = useState<VendorBill | null>(null);
  const [error, setError] = useState("");
  const refresh = async () => {
    const value = await getVendorBill(id);
    setBill(value);
  };
  useEffect(() => {
    if (!allowed) return;
    let active = true;
    getVendorBill(id)
      .then((value) => active && setBill(value))
      .catch(
        (e) =>
          active &&
          setError(
            e instanceof ApiError && e.status === 404
              ? "Vendor Bill not found."
              : e instanceof ApiError && e.status === 403
                ? "You do not have access to this Vendor Bill."
                : "The Vendor Bill could not be loaded.",
          ),
      );
    return () => {
      active = false;
    };
  }, [id, allowed]);
  return { bill, error, refresh };
}

function Detail({ bill }: { bill: VendorBill }) {
  return (
    <>
      <section className="detail-card">
        <dl className="detail-grid">
          <dt>Internal Bill Reference</dt>
          <dd>{bill.bill_number}</dd>
          <dt>Supplier Invoice Number</dt>
          <dd>{bill.vendor_invoice_number}</dd>
          <dt>Vendor</dt>
          <dd>
            {bill.vendor_code} — {bill.vendor_name}
          </dd>
          <dt>Bill date</dt>
          <dd>{bill.bill_date}</dd>
          <dt>Due date</dt>
          <dd>{bill.due_date}</dd>
          <dt>Match type</dt>
          <dd>{bill.match_type === "THREE_WAY" ? "Three-way" : "Two-way"}</dd>
          <dt>Status</dt>
          <dd>{statusLabel(bill.status)}</dd>
          <dt>Match exception</dt>
          <dd>{bill.match_exception || "—"}</dd>
        </dl>
      </section>
      <section className="detail-card">
        <h2>Financial summary</h2>
        <Totals bill={bill} />
      </section>
      <section className="detail-card">
        <h2>Line items</h2>
        {bill.lines?.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Description</th>
                  <th>Quantity</th>
                  <th>Unit price</th>
                  <th>Tax</th>
                  <th>Account</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {bill.lines.map((line) => (
                  <tr key={line.id}>
                    <td>{line.description}</td>
                    <td>{line.quantity}</td>
                    <td>{line.unit_price}</td>
                    <td>{line.tax_amount}</td>
                    <td>
                      {line.expense_account_code} — {line.expense_account_name}
                    </td>
                    <td>{line.line_total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>No line items recorded.</p>
        )}
      </section>
      <section className="detail-card">
        <h2>Payments</h2>
        {bill.payments?.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Voucher #</th>
                  <th>Payment date</th>
                  <th>Amount</th>
                  <th>Workflow</th>
                  <th>Payment status</th>
                  <th>Reference</th>
                </tr>
              </thead>
              <tbody>
                {bill.payments.map((payment) => (
                  <tr key={payment.id}>
                    <td>
                      <Link href={`/vendor-payments/${payment.id}`}>
                        {payment.voucher_number}
                      </Link>
                    </td>
                    <td>{payment.payment_date}</td>
                    <td>{payment.amount}</td>
                    <td>{statusLabel(payment.status)}</td>
                    <td>{statusLabel(payment.payment_status)}</td>
                    <td>{payment.payment_reference || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>No Vendor Payments recorded.</p>
        )}
      </section>
    </>
  );
}

export function VendorBillDetailPage({ id }: { id: string }) {
  const auth = useAuth();
  const allowed = auth.can("finance.view_vendorbill");
  const { bill, error, refresh } = useBill(id, allowed);
  if (!allowed)
    return (
      <ErrorState message="You do not have permission to view Vendor Bills." />
    );
  if (error) return <ErrorState message={error} />;
  if (!bill) return <LoadingState label="Loading Vendor Bill…" />;
  return (
    <>
      <PageHeader
        title={bill.bill_number}
        description={bill.vendor_name}
        actions={
          bill.status === "DRAFT" && auth.can("finance.change_vendorbill") ? (
            <Link className="button" href={`/vendor-bills/${bill.id}/edit`}>
              Edit Vendor Bill
            </Link>
          ) : undefined
        }
      />
      <VendorBillWorkflow bill={bill} refresh={refresh} />
      <Detail bill={bill} />
      <VendorBillDocuments billId={bill.id} />
    </>
  );
}

export function VendorBillEditPage({ id }: { id: string }) {
  const auth = useAuth();
  const allowed = auth.can("finance.view_vendorbill");
  const { bill, error, refresh } = useBill(id, allowed);
  if (!allowed)
    return (
      <ErrorState message="You do not have permission to view Vendor Bills." />
    );
  if (error) return <ErrorState message={error} />;
  if (!bill) return <LoadingState label="Loading Vendor Bill…" />;
  if (bill.status !== "DRAFT")
    return (
      <>
        <ErrorState message="This Vendor Bill can no longer be edited." />
        <Link className="button" href={`/vendor-bills/${bill.id}`}>
          Back to Vendor Bill
        </Link>
      </>
    );
  return (
    <>
      <PageHeader
        title={`Edit ${bill.bill_number}`}
        description="Draft Vendor Bills can be edited before submission."
      />
      <section className="detail-card">
        <h2>Bill header</h2>
        <HeaderForm bill={bill} />
      </section>
      <section className="detail-card">
        <h2>Financial summary</h2>
        <Totals bill={bill} />
      </section>
      <section className="detail-card">
        <h2>Line items</h2>
        <Lines bill={bill} refresh={refresh} />
      </section>
    </>
  );
}
