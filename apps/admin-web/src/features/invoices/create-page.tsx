"use client";

import { PageHeader } from "@/components/layout/page-header";
import { ErrorState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";

import { InvoiceCreateForm } from "./create-form";

export function NewInvoicePage() {
  const auth = useAuth();
  if (!auth.can("billing.add_clientinvoice"))
    return (
      <ErrorState message="You do not have permission to create invoices." />
    );
  return (
    <>
      <PageHeader
        title="New Invoice"
        description="Create a draft invoice for a billing profile."
      />
      <InvoiceCreateForm />
    </>
  );
}
