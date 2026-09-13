"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { ApiError } from "@/lib/api/client";

import { getInvoice } from "./api";
import { formatDate, formatMoney } from "./format";
import {
  InvoiceDetailSection,
  InvoiceLineTable,
  InvoiceStatusBadge,
  InvoiceTotals,
  Lifecycle,
  PrivateDocumentDownload,
} from "./components";
import type { InvoiceDetail } from "./types";
import { InvoiceWorkflowActions } from "./workflow-actions";

export function InvoiceDetailPage({ id }: { id: string }) {
  const auth = useAuth();
  const allowed = auth.can("billing.view_clientinvoice");
  const [invoice, setInvoice] = useState<InvoiceDetail | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!allowed) return;
    let active = true;
    getInvoice(id)
      .then((value) => active && setInvoice(value))
      .catch(
        (reason: unknown) =>
          active &&
          setError(
            reason instanceof ApiError && reason.status === 404
              ? "Invoice not found."
              : reason instanceof ApiError && reason.status === 403
                ? "You do not have access to invoices."
                : "The invoice could not be loaded. Please try again.",
          ),
      );
    return () => {
      active = false;
    };
  }, [allowed, id]);
  if (!allowed)
    return (
      <ErrorState message="You do not have permission to view invoices." />
    );
  if (error)
    return (
      <>
        <Link href="/invoices">← Back to invoices</Link>
        <ErrorState message={error} />
      </>
    );
  if (!invoice) return <LoadingState label="Loading invoice…" />;
  return (
    <>
      <div className="breadcrumb">
        <Link href="/invoices">Invoices</Link>
        <span aria-hidden="true">/</span>
        <span>{invoice.invoice_number}</span>
      </div>
      <PageHeader
        title={invoice.invoice_number || "Invoice"}
        description={invoice.billing_name_snapshot}
        actions={
          invoice.pdf_available && auth.can("billing.download_invoice") ? (
            <PrivateDocumentDownload invoiceId={invoice.id} />
          ) : undefined
        }
      />
      <div className="invoice-heading">
        <InvoiceStatusBadge status={invoice.status} />
        {invoice.is_overdue ? (
          <strong className="overdue-label">Overdue</strong>
        ) : null}
        <span>Invoice date {formatDate(invoice.invoice_date)}</span>
        <span>Due {formatDate(invoice.due_date)}</span>
      </div>
      <InvoiceWorkflowActions invoice={invoice} onChanged={setInvoice} />
      <InvoiceDetailSection title="Financial summary">
        <InvoiceTotals invoice={invoice} />
      </InvoiceDetailSection>
      <InvoiceDetailSection title="Line items">
        <InvoiceLineTable lines={invoice.lines} currency={invoice.currency} />
      </InvoiceDetailSection>
      <div className="detail-columns">
        <InvoiceDetailSection title="Details">
          <dl className="metadata-grid">
            <div>
              <dt>Client</dt>
              <dd>{invoice.billing_name_snapshot}</dd>
            </div>
            <div>
              <dt>Contract</dt>
              <dd>{invoice.contract ? "Linked contract" : "—"}</dd>
            </div>
            <div>
              <dt>Service period</dt>
              <dd>
                {formatDate(invoice.service_period_start)} –{" "}
                {formatDate(invoice.service_period_end)}
              </dd>
            </div>
            <div>
              <dt>Client reference</dt>
              <dd>{invoice.client_reference || "—"}</dd>
            </div>
            <div>
              <dt>PO reference</dt>
              <dd>{invoice.client_po_reference || "—"}</dd>
            </div>
          </dl>
        </InvoiceDetailSection>
        <InvoiceDetailSection title="Payment summary">
          <dl className="metadata-grid">
            <div>
              <dt>Total</dt>
              <dd>{formatMoney(invoice.total_amount, invoice.currency)}</dd>
            </div>
            <div>
              <dt>Paid</dt>
              <dd>{formatMoney(invoice.amount_paid, invoice.currency)}</dd>
            </div>
            <div>
              <dt>Outstanding</dt>
              <dd>{formatMoney(invoice.balance_due, invoice.currency)}</dd>
            </div>
            <div>
              <dt>Payment status</dt>
              <dd>
                <InvoiceStatusBadge status={invoice.status} />
              </dd>
            </div>
          </dl>
        </InvoiceDetailSection>
      </div>
      <InvoiceDetailSection title="Receipt allocations">
        {invoice.receipt_allocations?.length ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Receipt</th>
                  <th>Receipt date</th>
                  <th>Method / reference</th>
                  <th>Allocated</th>
                </tr>
              </thead>
              <tbody>
                {invoice.receipt_allocations.map((allocation) => (
                  <tr key={allocation.id}>
                    <td>
                      <Link href={`/receipts/${allocation.receipt}`}>
                        {allocation.receipt_number}
                      </Link>
                    </td>
                    <td>{formatDate(allocation.receipt_date)}</td>
                    <td>
                      {allocation.payment_method.replaceAll("_", " ")}
                      {allocation.reference ? ` · ${allocation.reference}` : ""}
                    </td>
                    <td>{formatMoney(allocation.amount, invoice.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>No receipt allocations are recorded.</p>
        )}
      </InvoiceDetailSection>
      <InvoiceDetailSection title="Lifecycle">
        <Lifecycle invoice={invoice} />
      </InvoiceDetailSection>
    </>
  );
}
