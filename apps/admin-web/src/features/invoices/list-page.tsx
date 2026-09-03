"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/layout/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { ApiError } from "@/lib/api/client";

import { listInvoices } from "./api";
import { InvoiceFilters, InvoiceTable, Pagination } from "./components";
import type { InvoiceDetail, PaginatedResponse } from "./types";

export function InvoiceListPage({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const auth = useAuth();
  const allowed = auth.can("billing.view_clientinvoice");
  const [data, setData] = useState<PaginatedResponse<InvoiceDetail> | null>(
    null,
  );
  const [error, setError] = useState("");
  const query = new URLSearchParams(searchParams);

  useEffect(() => {
    if (!allowed) return;

    let active = true;

    const load = async () => {
      setData(null);
      setError("");

      try {
        const value = await listInvoices(searchParams);
        if (active) setData(value);
      } catch (reason: unknown) {
        if (!active) return;
        const message =
          reason instanceof ApiError && reason.status === 401
            ? "Your session has expired. Sign in again."
            : reason instanceof ApiError && reason.status === 403
              ? "You do not have access to invoices."
              : "Invoices could not be loaded. Please try again.";
        setError(message);
      }
    };

    void load();
    return () => {
      active = false;
    };
  }, [allowed, searchParams]);

  if (!allowed)
    return (
      <ErrorState message="You do not have permission to view invoices." />
    );
  return (
    <>
      <PageHeader
        title="Invoices"
        description="Review issued and in-progress client invoices."
      />
      <InvoiceFilters values={searchParams} />
      {error ? (
        <ErrorState message={error} />
      ) : !data ? (
        <LoadingState label="Loading invoices…" />
      ) : !data.results.length ? (
        <EmptyState
          message={
            query.size
              ? "No invoices match these filters."
              : "No invoices found."
          }
        />
      ) : (
        <>
          <InvoiceTable invoices={data.results} />
          <Pagination
            count={data.count}
            page={Number(searchParams.page) || 1}
            hasNext={Boolean(data.next)}
            hasPrevious={Boolean(data.previous)}
            query={query}
          />
        </>
      )}
    </>
  );
}
