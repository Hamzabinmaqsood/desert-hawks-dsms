"use client";

import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { FormError } from "@/components/ui/form-field";
import { ApiError } from "@/lib/api/client";

import { updateInvoiceDraft } from "./api";
import { InvoiceHeaderFields, validateHeaderDates } from "./header-fields";
import { listContracts } from "./reference-api";
import type { Contract, InvoiceDetail } from "./types";

export function InvoiceHeaderEditForm({
  invoice,
  onSaved,
  onConflict,
}: {
  invoice: InvoiceDetail;
  onSaved: (invoice: InvoiceDetail) => void;
  onConflict: () => Promise<void>;
}) {
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [refError, setRefError] = useState("");
  const [values, setValues] = useState({
    contract: invoice.contract ?? "",
    invoice_date: invoice.invoice_date,
    service_period_start: invoice.service_period_start ?? "",
    service_period_end: invoice.service_period_end ?? "",
    client_po_reference: invoice.client_po_reference,
    client_reference: invoice.client_reference,
  });
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [nonFieldError, setNonFieldError] = useState<string>();
  const [submitting, setSubmitting] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let active = true;
    listContracts()
      .then((list) => {
        if (active)
          setContracts(
            list.filter((contract) => contract.client === invoice.client),
          );
      })
      .catch(() => {
        if (active) setRefError("Contracts could not be loaded.");
      });
    return () => {
      active = false;
    };
  }, [invoice.client]);

  function set(key: keyof typeof values, value: string) {
    setValues((current) => ({ ...current, [key]: value }));
    setSaved(false);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    const dateErrors = validateHeaderDates(values);
    if (Object.keys(dateErrors).length) {
      setErrors(dateErrors);
      return;
    }
    setSubmitting(true);
    setErrors({});
    setNonFieldError(undefined);
    try {
      const updated = await updateInvoiceDraft(invoice.id, {
        contract: values.contract || null,
        invoice_date: values.invoice_date,
        service_period_start: values.service_period_start || null,
        service_period_end: values.service_period_end || null,
        client_po_reference: values.client_po_reference,
        client_reference: values.client_reference,
      });
      onSaved(updated);
      setSaved(true);
    } catch (caught) {
      if (caught instanceof ApiError) {
        setErrors(caught.fieldErrors);
        setNonFieldError(caught.message);
      } else {
        setNonFieldError("The invoice could not be updated.");
      }
      await onConflict();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      className="invoice-form"
      onSubmit={submit}
      aria-label="Edit invoice details"
    >
      {refError ? <p className="field-error">{refError}</p> : null}
      <InvoiceHeaderFields
        values={values}
        errors={errors}
        onChange={set}
        contracts={contracts}
        disabled={submitting}
      />
      <FormError message={nonFieldError} />
      {saved ? <p role="status">Saved.</p> : null}
      <Button type="submit" disabled={submitting}>
        {submitting ? "Saving…" : "Save changes"}
      </Button>
    </form>
  );
}
