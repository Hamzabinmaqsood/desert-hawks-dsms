"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { FormError, FormField } from "@/components/ui/form-field";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import {
  formatDate,
  formatMoney,
  formatTimestamp,
} from "@/features/invoices/format";
import { ApiError } from "@/lib/api/client";

import {
  allocateReceipt,
  confirmReceipt,
  createReceipt,
  getReceipt,
  listEligibleInvoices,
  listReceiptBankAccounts,
  listReceiptClients,
  listReceipts,
} from "./api";
import {
  PAYMENT_METHODS,
  type EligibleInvoice,
  type Receipt,
  type ReceiptBankAccount,
  type ReceiptClient,
} from "./types";

function Status({ value }: { value: string }) {
  return (
    <span className={`status-badge status-${value.toLowerCase()}`}>
      {value.replaceAll("_", " ")}
    </span>
  );
}

export function ReceiptListPage({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const auth = useAuth();
  const [data, setData] = useState<Awaited<
    ReturnType<typeof listReceipts>
  > | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (auth.can("billing.view_clientreceipt"))
      listReceipts(searchParams)
        .then(setData)
        .catch(() => setError("Receipts could not be loaded."));
  }, [auth, searchParams]);
  if (!auth.can("billing.view_clientreceipt"))
    return (
      <ErrorState message="You do not have permission to view receipts." />
    );
  return (
    <>
      <PageHeader
        title="Receipts"
        description="Record client payments and allocate confirmed funds to invoices."
        actions={
          auth.can("billing.add_clientreceipt") ? (
            <Link className="button" href="/receipts/new">
              New Receipt
            </Link>
          ) : undefined
        }
      />
      <form className="invoice-filters" action="/receipts">
        <label>
          Search
          <input
            name="search"
            defaultValue={searchParams.search}
            placeholder="Receipt number or reference"
          />
        </label>
        <label>
          Status
          <select name="status" defaultValue={searchParams.status}>
            <option value="">All statuses</option>
            {[
              "DRAFT",
              "CONFIRMED",
              "PARTIALLY_ALLOCATED",
              "ALLOCATED",
              "REVERSED",
              "CANCELLED",
            ].map((x) => (
              <option key={x}>{x}</option>
            ))}
          </select>
        </label>
        <label>
          Payment method
          <select
            name="payment_method"
            defaultValue={searchParams.payment_method}
          >
            <option value="">All methods</option>
            {PAYMENT_METHODS.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <div className="filter-actions">
          <Button type="submit">Apply</Button>
          <Link className="button button-secondary" href="/receipts">
            Clear
          </Link>
        </div>
      </form>
      {error ? (
        <ErrorState message={error} />
      ) : !data ? (
        <LoadingState label="Loading receipts…" />
      ) : !data.results.length ? (
        <EmptyState message="No receipts found." />
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Receipt</th>
                <th>Client</th>
                <th>Date</th>
                <th>Method</th>
                <th>Reference</th>
                <th>Amount</th>
                <th>Allocated</th>
                <th>Unallocated</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link href={`/receipts/${r.id}`}>{r.receipt_number}</Link>
                  </td>
                  <td>{r.client_name}</td>
                  <td>{formatTimestamp(r.received_at)}</td>
                  <td>{r.payment_method.replaceAll("_", " ")}</td>
                  <td>{r.external_reference || r.cheque_reference || "—"}</td>
                  <td>{formatMoney(r.amount, r.currency)}</td>
                  <td>{formatMoney(r.allocated_amount, r.currency)}</td>
                  <td>{formatMoney(r.unallocated_amount, r.currency)}</td>
                  <td>
                    <Status value={r.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export function ReceiptCreatePage() {
  const auth = useAuth();
  const router = useRouter();
  const [profiles, setProfiles] = useState<ReceiptClient[]>([]);
  const [banks, setBanks] = useState<ReceiptBankAccount[]>([]);
  const [values, setValues] = useState({
    profile: "",
    received_at: "",
    value_date: "",
    amount: "",
    payment_method: "",
    bank_account: "",
    cheque_reference: "",
    external_reference: "",
    notes: "",
  });
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [message, setMessage] = useState<string>();
  const [pending, setPending] = useState(false);
  useEffect(() => {
    Promise.all([listReceiptClients(), listReceiptBankAccounts()])
      .then(([p, b]) => {
        setProfiles(p);
        setBanks(b);
      })
      .catch(() => setMessage("Reference data could not be loaded."));
  }, []);
  if (!auth.can("billing.add_clientreceipt"))
    return (
      <ErrorState message="You do not have permission to create receipts." />
    );
  const profile = profiles.find((p) => p.client === values.profile);
  const availableBanks = banks.filter(
    (b) =>
      !profile ||
      (b.company === profile.company && b.currency === profile.currency),
  );
  const set = (key: keyof typeof values, value: string) =>
    setValues((current) => ({
      ...current,
      [key]: value,
      ...(key === "profile" ? { bank_account: "" } : {}),
    }));
  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setErrors({});
    setMessage(undefined);
    try {
      if (!profile) throw new Error();
      const created = await createReceipt({
        company: profile.company,
        client: profile.client,
        received_at: new Date(values.received_at).toISOString(),
        value_date: values.value_date || null,
        currency: profile.currency,
        amount: values.amount,
        payment_method: values.payment_method,
        bank_account: values.bank_account || null,
        cheque_reference: values.cheque_reference,
        external_reference: values.external_reference,
        notes: values.notes,
      });
      router.push(`/receipts/${created.id}`);
    } catch (e) {
      if (e instanceof ApiError) {
        setErrors(e.fieldErrors);
        setMessage(e.message);
      } else setMessage("The receipt could not be created.");
    } finally {
      setPending(false);
    }
  }
  return (
    <>
      <PageHeader
        title="New Receipt"
        description="Record a client payment as a draft for independent confirmation."
      />
      <form className="invoice-form" aria-label="New receipt" onSubmit={submit}>
        <label className="form-field">
          <span>Client</span>
          <select
            required
            value={values.profile}
            onChange={(e) => set("profile", e.target.value)}
          >
            <option value="">Select a client</option>
            {profiles.map((p) => (
              <option key={p.client} value={p.client}>
                {p.billing_name} ({p.currency})
              </option>
            ))}
          </select>
          {errors.client?.[0] && (
            <span className="field-error">{errors.client[0]}</span>
          )}
        </label>
        <FormField
          id="received_at"
          label="Received at"
          type="datetime-local"
          required
          value={values.received_at}
          onChange={(e) => set("received_at", e.target.value)}
          error={errors.received_at?.[0]}
        />
        <FormField
          id="value_date"
          label="Value date"
          type="date"
          value={values.value_date}
          onChange={(e) => set("value_date", e.target.value)}
          error={errors.value_date?.[0]}
        />
        <FormField
          id="amount"
          label="Amount"
          inputMode="decimal"
          required
          value={values.amount}
          onChange={(e) => set("amount", e.target.value)}
          error={errors.amount?.[0]}
        />
        <label className="form-field">
          <span>Payment method</span>
          <select
            required
            value={values.payment_method}
            onChange={(e) => set("payment_method", e.target.value)}
          >
            <option value="">Select a method</option>
            {PAYMENT_METHODS.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
          {errors.payment_method?.[0] && (
            <span className="field-error">{errors.payment_method[0]}</span>
          )}
        </label>
        <label className="form-field">
          <span>Receiving bank account</span>
          <select
            value={values.bank_account}
            onChange={(e) => set("bank_account", e.target.value)}
          >
            <option value="">Select an account</option>
            {availableBanks.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name} · {b.bank_name} ({b.currency})
              </option>
            ))}
          </select>
          {errors.bank_account?.[0] && (
            <span className="field-error">{errors.bank_account[0]}</span>
          )}
        </label>
        <FormField
          id="external_reference"
          label="External reference"
          value={values.external_reference}
          onChange={(e) => set("external_reference", e.target.value)}
          error={errors.external_reference?.[0]}
        />
        <FormField
          id="cheque_reference"
          label="Cheque reference"
          value={values.cheque_reference}
          onChange={(e) => set("cheque_reference", e.target.value)}
          error={errors.cheque_reference?.[0]}
        />
        <FormField
          id="notes"
          label="Notes"
          value={values.notes}
          onChange={(e) => set("notes", e.target.value)}
          error={errors.notes?.[0]}
        />
        <FormError message={message} />
        <div className="filter-actions">
          <Button disabled={pending}>
            {pending ? "Creating…" : "Create draft"}
          </Button>
          <Link className="button button-secondary" href="/receipts">
            Cancel
          </Link>
        </div>
      </form>
    </>
  );
}

export function ReceiptDetailPage({ id }: { id: string }) {
  const auth = useAuth();
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [invoices, setInvoices] = useState<EligibleInvoice[]>([]);
  const [invoice, setInvoice] = useState("");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [pending, setPending] = useState(false);
  const canAllocate = auth.can("billing.allocate_receipt");
  const refresh = async () => {
    const value = await getReceipt(id);
    setReceipt(value);
    if (
      canAllocate &&
      ["CONFIRMED", "PARTIALLY_ALLOCATED"].includes(value.status)
    )
      setInvoices(await listEligibleInvoices(id));
    else setInvoices([]);
  };
  useEffect(() => {
    if (!auth.can("billing.view_clientreceipt")) return;
    getReceipt(id)
      .then(async (value) => {
        setReceipt(value);
        setInvoices(
          canAllocate &&
            ["CONFIRMED", "PARTIALLY_ALLOCATED"].includes(value.status)
            ? await listEligibleInvoices(id)
            : [],
        );
      })
      .catch(() => setError("The receipt could not be loaded."));
  }, [auth, canAllocate, id]);
  if (!auth.can("billing.view_clientreceipt"))
    return (
      <ErrorState message="You do not have permission to view receipts." />
    );
  if (error && !receipt) return <ErrorState message={error} />;
  if (!receipt) return <LoadingState label="Loading receipt…" />;
  const selected = invoices.find((i) => i.id === invoice);
  async function confirm() {
    setPending(true);
    setError("");
    try {
      await confirmReceipt(id);
      await refresh();
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "The receipt could not be confirmed.",
      );
    } finally {
      setPending(false);
    }
  }
  async function allocate(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    setFieldErrors({});
    try {
      await allocateReceipt(id, invoice, amount);
      setInvoice("");
      setAmount("");
      await refresh();
    } catch (e) {
      if (e instanceof ApiError) {
        setFieldErrors(e.fieldErrors);
        setError(Object.values(e.fieldErrors).flat()[0] ?? e.message);
      } else setError("The allocation could not be created.");
      await refresh().catch(() => undefined);
    } finally {
      setPending(false);
    }
  }
  return (
    <>
      <div className="breadcrumb">
        <Link href="/receipts">Receipts</Link>
        <span>/</span>
        <span>{receipt.receipt_number}</span>
      </div>
      <PageHeader
        title={receipt.receipt_number}
        description={receipt.client_name}
      />
      <div className="invoice-heading">
        <Status value={receipt.status} />
        <span>Received {formatTimestamp(receipt.received_at)}</span>
      </div>
      {receipt.status === "DRAFT" && auth.can("billing.confirm_receipt") ? (
        <div className="workflow-actions">
          <Button disabled={pending} onClick={confirm}>
            {pending ? "Confirming…" : "Confirm receipt"}
          </Button>
        </div>
      ) : null}
      {error ? <FormError message={error} /> : null}
      <section className="detail-section">
        <h2>Payment summary</h2>
        <dl className="totals-grid">
          <div>
            <dt>Amount</dt>
            <dd>{formatMoney(receipt.amount, receipt.currency)}</dd>
          </div>
          <div>
            <dt>Allocated</dt>
            <dd>{formatMoney(receipt.allocated_amount, receipt.currency)}</dd>
          </div>
          <div>
            <dt>Unallocated</dt>
            <dd>{formatMoney(receipt.unallocated_amount, receipt.currency)}</dd>
          </div>
          <div>
            <dt>Method</dt>
            <dd>{receipt.payment_method.replaceAll("_", " ")}</dd>
          </div>
          <div>
            <dt>Value date</dt>
            <dd>{formatDate(receipt.value_date)}</dd>
          </div>
          <div>
            <dt>Reference</dt>
            <dd>
              {receipt.external_reference || receipt.cheque_reference || "—"}
            </dd>
          </div>
        </dl>
      </section>
      {canAllocate &&
      ["CONFIRMED", "PARTIALLY_ALLOCATED"].includes(receipt.status) ? (
        <section className="detail-section">
          <h2>Allocate to invoice</h2>
          {invoices.length ? (
            <form className="allocation-form" onSubmit={allocate}>
              <label className="form-field">
                <span>Eligible invoice</span>
                <select
                  required
                  value={invoice}
                  onChange={(e) => setInvoice(e.target.value)}
                >
                  <option value="">Select an invoice</option>
                  {invoices.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.invoice_number} ·{" "}
                      {formatMoney(i.balance_due, i.currency)} outstanding
                    </option>
                  ))}
                </select>
                {fieldErrors.invoice?.[0] && (
                  <span className="field-error">{fieldErrors.invoice[0]}</span>
                )}
              </label>
              <FormField
                id="allocation_amount"
                label="Allocation amount"
                inputMode="decimal"
                required
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                error={fieldErrors.amount?.[0]}
              />
              {selected ? (
                <p className="form-hint">
                  Invoice outstanding:{" "}
                  {formatMoney(selected.balance_due, selected.currency)} ·
                  Receipt available:{" "}
                  {formatMoney(receipt.unallocated_amount, receipt.currency)}
                </p>
              ) : null}
              <Button disabled={pending}>
                {pending ? "Allocating…" : "Allocate payment"}
              </Button>
            </form>
          ) : (
            <EmptyState message="No eligible invoices have an outstanding balance for this client." />
          )}
        </section>
      ) : null}
      <section className="detail-section">
        <h2>Allocation history</h2>
        {receipt.allocations.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Amount</th>
                  <th>Allocated</th>
                </tr>
              </thead>
              <tbody>
                {receipt.allocations.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <Link href={`/invoices/${a.invoice}`}>
                        {a.invoice_number}
                      </Link>
                    </td>
                    <td>{formatMoney(a.amount, receipt.currency)}</td>
                    <td>{formatTimestamp(a.allocated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState message="No allocations have been recorded." />
        )}
      </section>
    </>
  );
}
