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
  createVendorPayment,
  getVendorPayment,
  listPayableBills,
  listPaymentAccounts,
  listVendorPayments,
  payVendorPayment,
  runVendorPaymentAction,
} from "./api";
import type { PayableBill, PaymentAccount, VendorPayment } from "./types";

const label = (value: string) => value.replaceAll("_", " ");

export function VendorPaymentListPage() {
  const auth = useAuth();
  const [items, setItems] = useState<VendorPayment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    listVendorPayments({})
      .then((page) => setItems(page.results))
      .catch(() => setError("Vendor Payments could not be loaded."))
      .finally(() => setLoading(false));
  }, []);
  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;
  return (
    <>
      <PageHeader
        title="Vendor Payments"
        description="Settle posted Vendor Bills through controlled Payment Vouchers."
        actions={
          auth.can("finance.add_paymentvoucher") ? (
            <Link className="button" href="/vendor-payments/new">
              New Vendor Payment
            </Link>
          ) : undefined
        }
      />
      {!items.length ? (
        <EmptyState message="No Vendor Payments" />
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Voucher #</th>
                <th>Bill</th>
                <th>Vendor</th>
                <th>Date</th>
                <th>Amount</th>
                <th>Workflow</th>
                <th>Payment</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <Link href={`/vendor-payments/${item.id}`}>
                      {item.voucher_number}
                    </Link>
                  </td>
                  <td>{item.bill_number}</td>
                  <td>{item.vendor_name}</td>
                  <td>{item.payment_date}</td>
                  <td>{item.amount}</td>
                  <td>{label(item.status)}</td>
                  <td>{label(item.payment_status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export function VendorPaymentCreatePage() {
  const auth = useAuth();
  const router = useRouter();
  const [bills, setBills] = useState<PayableBill[]>([]);
  const [values, setValues] = useState({
    vendor_bill: "",
    voucher_number: "",
    payment_date: "",
    amount: "",
    payment_reference: "",
  });
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  useEffect(() => {
    listPayableBills()
      .then(setBills)
      .catch(() => setMessage("Payable Bills could not be loaded."));
  }, []);
  if (!auth.can("finance.add_paymentvoucher"))
    return (
      <ErrorState message="You do not have permission to create Vendor Payments." />
    );
  const set = (key: keyof typeof values, value: string) =>
    setValues((current) => ({ ...current, [key]: value }));
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setErrors({});
    setMessage("");
    try {
      const saved = await createVendorPayment(values);
      router.push(`/vendor-payments/${saved.id}`);
    } catch (cause) {
      if (cause instanceof ApiError) {
        setErrors(cause.fieldErrors);
        setMessage(cause.message);
      } else setMessage("The Vendor Payment could not be created.");
    } finally {
      setPending(false);
    }
  }
  return (
    <>
      <PageHeader
        title="New Vendor Payment"
        description="Create a draft Payment Voucher against one payable Vendor Bill."
      />
      <form
        className="invoice-form"
        onSubmit={submit}
        aria-label="New Vendor Payment"
      >
        <label className="form-field">
          <span>Vendor Bill</span>
          <select
            required
            value={values.vendor_bill}
            disabled={pending}
            onChange={(e) => set("vendor_bill", e.target.value)}
          >
            <option value="">Select a payable Bill</option>
            {bills.map((bill) => (
              <option key={bill.id} value={bill.id}>
                {bill.bill_number} — {bill.vendor_name} —{" "}
                {bill.outstanding_amount}
              </option>
            ))}
          </select>
          {errors.vendor_bill?.[0] ? (
            <span className="field-error">{errors.vendor_bill[0]}</span>
          ) : null}
        </label>
        <FormField
          id="voucher_number"
          label="Voucher number"
          required
          value={values.voucher_number}
          onChange={(e) => set("voucher_number", e.target.value)}
          error={errors.voucher_number?.[0]}
        />
        <FormField
          id="payment_date"
          label="Payment date"
          type="date"
          required
          value={values.payment_date}
          onChange={(e) => set("payment_date", e.target.value)}
          error={errors.payment_date?.[0]}
        />
        <FormField
          id="amount"
          label="Amount"
          type="number"
          required
          value={values.amount}
          onChange={(e) => set("amount", e.target.value)}
          error={errors.amount?.[0]}
        />
        <FormField
          id="payment_reference"
          label="Reference"
          value={values.payment_reference}
          onChange={(e) => set("payment_reference", e.target.value)}
          error={errors.payment_reference?.[0]}
        />
        <FormError message={message} />
        <div className="filter-actions">
          <Button disabled={pending}>
            {pending ? "Saving..." : "Create draft"}
          </Button>
          <Link className="button button-secondary" href="/vendor-payments">
            Cancel
          </Link>
        </div>
      </form>
    </>
  );
}

export function VendorPaymentDetailPage({ id }: { id: string }) {
  const auth = useAuth();
  const [item, setItem] = useState<VendorPayment | null>(null);
  const [accounts, setAccounts] = useState<PaymentAccount[]>([]);
  const [account, setAccount] = useState("");
  const [reference, setReference] = useState("");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const refresh = useCallback(() => getVendorPayment(id).then(setItem), [id]);
  useEffect(() => {
    refresh().catch(() => setError("The Vendor Payment could not be loaded."));
  }, [refresh]);
  useEffect(() => {
    if (item?.status === "APPROVED" && auth.can("finance.post_journal"))
      listPaymentAccounts()
        .then(setAccounts)
        .catch(() => setError("Payment accounts could not be loaded."));
  }, [auth, item?.status]);
  async function action(name: "submit" | "approve" | "reject" | "pay") {
    if (pending || !item) return;
    if (
      !window.confirm(
        `${name === "pay" ? "Pay" : label(name)} this Vendor Payment?`,
      )
    )
      return;
    setPending(true);
    setError("");
    try {
      if (name === "pay") await payVendorPayment(item.id, account, reference);
      else await runVendorPaymentAction(item.id, name, reason);
      await refresh();
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "The workflow action failed.",
      );
      try {
        await refresh();
      } catch {}
    } finally {
      setPending(false);
    }
  }
  if (error && !item) return <ErrorState message={error} />;
  if (!item) return <LoadingState />;
  return (
    <>
      <PageHeader
        title={item.voucher_number}
        description={`${item.vendor_name} · ${item.bill_number}`}
      />
      <section className="detail-card">
        <dl className="detail-grid">
          <div>
            <dt>Amount</dt>
            <dd>{item.amount}</dd>
          </div>
          <div>
            <dt>Workflow</dt>
            <dd>{label(item.status)}</dd>
          </div>
          <div>
            <dt>Payment status</dt>
            <dd>{label(item.payment_status)}</dd>
          </div>
          <div>
            <dt>Reference</dt>
            <dd>{item.payment_reference || "—"}</dd>
          </div>
        </dl>
        <Link href={`/vendor-bills/${item.vendor_bill}`}>Open Vendor Bill</Link>
      </section>
      <section
        className="workflow-actions"
        aria-label="Vendor Payment workflow"
      >
        {item.status === "DRAFT" &&
        auth.can("finance.change_paymentvoucher") ? (
          <Button disabled={pending} onClick={() => void action("submit")}>
            Submit for approval
          </Button>
        ) : null}
        {item.status === "SUBMITTED" && auth.can("finance.approve_finance") ? (
          <div className="filter-actions">
            <Button disabled={pending} onClick={() => void action("approve")}>
              Approve
            </Button>
            <input
              aria-label="Rejection reason"
              placeholder="Rejection reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <Button
              className="button-secondary"
              disabled={pending || !reason.trim()}
              onClick={() => void action("reject")}
            >
              Reject
            </Button>
          </div>
        ) : null}
        {item.status === "APPROVED" && auth.can("finance.post_journal") ? (
          <div className="invoice-form">
            <label className="form-field">
              <span>Payment account</span>
              <select
                aria-label="Payment account"
                value={account}
                onChange={(e) => setAccount(e.target.value)}
              >
                <option value="">Select cash or bank account</option>
                {accounts.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.code} — {option.name}
                  </option>
                ))}
              </select>
            </label>
            <FormField
              id="payment_reference"
              label="Payment reference"
              value={reference}
              onChange={(e) => setReference(e.target.value)}
            />
            <Button
              disabled={pending || !account}
              onClick={() => void action("pay")}
            >
              Pay Vendor
            </Button>
          </div>
        ) : null}
        {error ? (
          <p className="field-error" role="alert">
            {error}
          </p>
        ) : null}
      </section>
    </>
  );
}
