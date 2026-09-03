"use client";

import { FormField } from "@/components/ui/form-field";

import type { Contract } from "./types";

export interface InvoiceHeaderValues {
  contract: string;
  invoice_date: string;
  service_period_start: string;
  service_period_end: string;
  client_po_reference: string;
  client_reference: string;
}

export function InvoiceHeaderFields({
  values,
  errors,
  onChange,
  contracts,
  disabled,
}: {
  values: InvoiceHeaderValues;
  errors: Record<string, string[]>;
  onChange: (key: keyof InvoiceHeaderValues, value: string) => void;
  contracts: Contract[];
  disabled?: boolean;
}) {
  return (
    <>
      <FormField
        id="invoice_date"
        label="Invoice date"
        type="date"
        required
        value={values.invoice_date}
        onChange={(event) => onChange("invoice_date", event.target.value)}
        error={errors.invoice_date?.[0]}
        disabled={disabled}
      />
      <label className="form-field">
        <span>Contract</span>
        <select
          value={values.contract}
          onChange={(event) => onChange("contract", event.target.value)}
          disabled={disabled}
        >
          <option value="">No contract</option>
          {contracts.map((contract) => (
            <option key={contract.id} value={contract.id}>
              {contract.contract_number} — {contract.title}
            </option>
          ))}
        </select>
        {errors.contract?.[0] ? (
          <span className="field-error">{errors.contract[0]}</span>
        ) : null}
      </label>
      <FormField
        id="service_period_start"
        label="Service period start"
        type="date"
        value={values.service_period_start}
        onChange={(event) =>
          onChange("service_period_start", event.target.value)
        }
        error={errors.service_period_start?.[0]}
        disabled={disabled}
      />
      <FormField
        id="service_period_end"
        label="Service period end"
        type="date"
        value={values.service_period_end}
        onChange={(event) => onChange("service_period_end", event.target.value)}
        error={errors.service_period_end?.[0]}
        disabled={disabled}
      />
      <FormField
        id="client_po_reference"
        label="Client PO reference"
        value={values.client_po_reference}
        onChange={(event) =>
          onChange("client_po_reference", event.target.value)
        }
        error={errors.client_po_reference?.[0]}
        disabled={disabled}
      />
      <FormField
        id="client_reference"
        label="Client reference"
        value={values.client_reference}
        onChange={(event) => onChange("client_reference", event.target.value)}
        error={errors.client_reference?.[0]}
        disabled={disabled}
      />
    </>
  );
}

export function validateHeaderDates(
  values: InvoiceHeaderValues,
): Record<string, string[]> {
  if (
    values.service_period_start &&
    values.service_period_end &&
    values.service_period_start > values.service_period_end
  ) {
    return {
      service_period_end: [
        "Service period end must be on or after the start date.",
      ],
    };
  }
  return {};
}
