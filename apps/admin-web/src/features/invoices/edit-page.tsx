"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { ApiError } from "@/lib/api/client";

import { getInvoice } from "./api";
import {
  InvoiceDetailSection,
  InvoiceStatusBadge,
  InvoiceTotals,
} from "./components";
import { InvoiceHeaderEditForm } from "./header-edit-form";
import { InvoiceLineEditor } from "./line-editor";
import type { InvoiceDetail } from "./types";

export function InvoiceEditPage({ id }: { id: string }) {
  const auth = useAuth();
  const canView = auth.can("billing.view_clientinvoice");
  const canEdit = auth.can("billing.change_clientinvoice");
  const [invoice, setInvoice] = useState<InvoiceDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!canView || !canEdit) return;
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
                ? "You do not have access to this invoice."
                : "The invoice could not be loaded. Please try again.",
          ),
      );
    return () => {
      active = false;
    };
  }, [canView, canEdit, id]);

  async function refresh() {
    try {
      const refreshed = await getInvoice(id);
      setInvoice(refreshed);
    } catch {
      // keep showing the current error state; nothing more we can do here
    }
  }

  if (!canView)
    return (
      <ErrorState message="You do not have permission to view invoices." />
    );
  if (!canEdit)
    return (
      <ErrorState message="You do not have permission to edit invoices." />
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
        <Link href={`/invoices/${invoice.id}`}>{invoice.invoice_number}</Link>
        <span aria-hidden="true">/</span>
        <span>Edit</span>
      </div>
      <PageHeader
        title={`Edit ${invoice.invoice_number}`}
        description="Draft invoices can be edited before submission."
      />
      <div className="invoice-heading">
        <InvoiceStatusBadge status={invoice.status} />
      </div>
      {invoice.status !== "DRAFT" ? (
        <>
          <ErrorState message="This invoice can no longer be edited." />
          <Link className="button" href={`/invoices/${invoice.id}`}>
            Back to invoice
          </Link>
        </>
      ) : (
        <>
          <InvoiceDetailSection title="Invoice details">
            <InvoiceHeaderEditForm
              invoice={invoice}
              onSaved={setInvoice}
              onConflict={refresh}
            />
          </InvoiceDetailSection>
          <InvoiceDetailSection title="Financial summary">
            <InvoiceTotals invoice={invoice} />
          </InvoiceDetailSection>
          <InvoiceDetailSection title="Line items">
            <InvoiceLineEditor
              invoice={invoice}
              onChanged={setInvoice}
              onConflict={refresh}
            />
          </InvoiceDetailSection>
          <div className="filter-actions">
            <Link className="button" href={`/invoices/${invoice.id}`}>
              Back to invoice
            </Link>
            <Link className="button button-secondary" href="/invoices">
              Back to invoices
            </Link>
          </div>
        </>
      )}
    </>
  );
}
