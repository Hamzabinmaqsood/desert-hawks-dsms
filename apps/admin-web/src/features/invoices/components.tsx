"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { downloadInvoice } from "./api";
import { formatDate, formatMoney, formatTimestamp } from "./format";
import type { InvoiceDetail, InvoiceLine, InvoiceStatus } from "./types";

const statusLabels: Record<InvoiceStatus, string> = {
  DRAFT: "Draft",
  UNDER_REVIEW: "Under review",
  APPROVED: "Approved",
  ISSUED: "Issued",
  PARTIALLY_PAID: "Partially paid",
  PAID: "Paid",
  VOIDED: "Voided",
  CANCELLED: "Cancelled",
};

export function InvoiceStatusBadge({ status }: { status: InvoiceStatus }) {
  return (
    <span
      className={`status-badge status-${status.toLowerCase()}`}
      role="status"
      aria-live="polite"
    >
      {statusLabels[status] ?? status.replaceAll("_", " ")}
    </span>
  );
}

export function InvoiceTable({ invoices }: { invoices: InvoiceDetail[] }) {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Invoice</th>
            <th>Client</th>
            <th>Invoice date</th>
            <th>Due date</th>
            <th>Status</th>
            <th>Total</th>
            <th>Paid</th>
            <th>Outstanding</th>
          </tr>
        </thead>
        <tbody>
          {invoices.map((invoice) => (
            <tr
              key={invoice.id}
              className={invoice.is_overdue ? "overdue-row" : undefined}
            >
              <td>
                <Link href={`/invoices/${invoice.id}`}>
                  {invoice.invoice_number || invoice.id}
                </Link>
                {invoice.is_overdue ? (
                  <span className="overdue-label">Overdue</span>
                ) : null}
              </td>
              <td>{invoice.billing_name_snapshot}</td>
              <td>{formatDate(invoice.invoice_date)}</td>
              <td>{formatDate(invoice.due_date)}</td>
              <td>
                <InvoiceStatusBadge status={invoice.status} />
              </td>
              <td>{formatMoney(invoice.total_amount, invoice.currency)}</td>
              <td>{formatMoney(invoice.amount_paid, invoice.currency)}</td>
              <td>{formatMoney(invoice.balance_due, invoice.currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function InvoiceFilters({ values }: { values: Record<string, string> }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  function submit(formData: FormData) {
    setPending(true);
    const query = new URLSearchParams();
    for (const key of ["search", "status", "invoice_type", "ordering"])
      if (formData.get(key)) query.set(key, String(formData.get(key)));
    router.push(`/invoices${query.size ? `?${query}` : ""}`);
  }
  return (
    <form
      className="invoice-filters"
      action={submit}
      aria-label="Invoice filters"
    >
      <label>
        Search
        <input
          name="search"
          defaultValue={values.search}
          placeholder="Number or reference"
        />
      </label>
      <label>
        Status
        <select name="status" defaultValue={values.status}>
          <option value="">All statuses</option>
          {Object.entries(statusLabels).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Type
        <input
          name="invoice_type"
          defaultValue={values.invoice_type}
          placeholder="Invoice type"
        />
      </label>
      <label>
        Sort
        <select name="ordering" defaultValue={values.ordering}>
          <option value="">Newest first</option>
          <option value="invoice_date">Invoice date ↑</option>
          <option value="-invoice_date">Invoice date ↓</option>
          <option value="due_date">Due date ↑</option>
          <option value="-due_date">Due date ↓</option>
          <option value="total_amount">Total ↑</option>
          <option value="-total_amount">Total ↓</option>
        </select>
      </label>
      <div className="filter-actions">
        <button className="button" disabled={pending} type="submit">
          {pending ? "Applying…" : "Apply"}
        </button>
        <Link className="button button-secondary" href="/invoices">
          Clear
        </Link>
      </div>
    </form>
  );
}

export function Pagination({
  count,
  page,
  hasNext,
  hasPrevious,
  query,
}: {
  count: number;
  page: number;
  hasNext: boolean;
  hasPrevious: boolean;
  query: URLSearchParams;
}) {
  const href = (nextPage: number) => {
    const params = new URLSearchParams(query);
    params.set("page", String(nextPage));
    return `/invoices?${params}`;
  };
  return (
    <nav className="pagination" aria-label="Invoice pagination">
      <span>
        {count} invoice{count === 1 ? "" : "s"} · Page {page}
      </span>
      <div>
        {hasPrevious ? (
          <Link className="button button-secondary" href={href(page - 1)}>
            Previous
          </Link>
        ) : null}
        {hasNext ? (
          <Link className="button button-secondary" href={href(page + 1)}>
            Next
          </Link>
        ) : null}
      </div>
    </nav>
  );
}

export function InvoiceTotals({ invoice }: { invoice: InvoiceDetail }) {
  const entries = [
    ["Subtotal", invoice.subtotal],
    ["Discount", invoice.discount_total],
    ["Tax", invoice.tax_total],
    ["Adjustment", invoice.adjustment_total],
    ["Total", invoice.total_amount],
    ["Paid", invoice.amount_paid],
    ["Outstanding", invoice.balance_due],
  ];
  return (
    <dl className="totals-grid">
      {entries.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{formatMoney(value, invoice.currency)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function InvoiceLineTable({
  lines,
  currency,
}: {
  lines: InvoiceLine[];
  currency: string;
}) {
  if (!lines.length) return <p>No line items are recorded.</p>;
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Description</th>
            <th>Quantity</th>
            <th>Unit</th>
            <th>Unit price</th>
            <th>Discount</th>
            <th>Tax</th>
            <th>Line total</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => (
            <tr key={line.id}>
              <td>{line.line_number}</td>
              <td>{line.description}</td>
              <td>{line.quantity}</td>
              <td>{line.unit}</td>
              <td>{formatMoney(line.unit_price, currency)}</td>
              <td>{formatMoney(line.discount_amount, currency)}</td>
              <td>{formatMoney(line.tax_amount, currency)}</td>
              <td>{formatMoney(line.line_total, currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function InvoiceDetailSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="detail-section">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

export function Lifecycle({ invoice }: { invoice: InvoiceDetail }) {
  return (
    <dl className="metadata-grid">
      <div>
        <dt>Created</dt>
        <dd>{formatTimestamp(invoice.created_at)}</dd>
      </div>
      <div>
        <dt>Reviewed</dt>
        <dd>{formatTimestamp(invoice.reviewed_at)}</dd>
      </div>
      <div>
        <dt>Approved</dt>
        <dd>{formatTimestamp(invoice.approved_at)}</dd>
      </div>
      <div>
        <dt>Issued</dt>
        <dd>{formatTimestamp(invoice.issued_at)}</dd>
      </div>
      <div>
        <dt>Posted</dt>
        <dd>{formatTimestamp(invoice.posted_at)}</dd>
      </div>
    </dl>
  );
}

export function PrivateDocumentDownload({ invoiceId }: { invoiceId: string }) {
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  async function download() {
    setPending(true);
    setError("");
    try {
      const response = await downloadInvoice(invoiceId);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download =
        response.headers
          .get("content-disposition")
          ?.match(/filename="?([^";]+)"?/)?.[1] ?? "invoice.pdf";
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("The invoice PDF could not be downloaded.");
    } finally {
      setPending(false);
    }
  }
  return (
    <div>
      <button
        className="button"
        type="button"
        disabled={pending}
        onClick={download}
      >
        {pending ? "Downloading…" : "Download PDF"}
      </button>
      {error ? (
        <p className="field-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
