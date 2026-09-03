"use client";

import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { FormError, FormField } from "@/components/ui/form-field";
import { ApiError } from "@/lib/api/client";

import {
  addInvoiceLine,
  deleteInvoiceLine,
  getInvoice,
  updateInvoiceLine,
} from "./api";
import { formatMoney } from "./format";
import {
  listAccounts,
  listBillingRules,
  listContractServices,
  listSites,
} from "./reference-api";
import type {
  AccountOption,
  BillingRuleOption,
  ContractServiceOption,
  InvoiceDetail,
  InvoiceLine,
  SiteOption,
} from "./types";

const emptyForm = {
  description: "",
  quantity: "",
  unit: "SERVICE",
  unit_price: "",
  discount_amount: "0.00",
  tax_rate: "0.00",
  revenue_account: "",
  contract_service: "",
  site: "",
  billing_rule: "",
};

type LineForm = typeof emptyForm;

const decimal = /^\d+(\.\d+)?$/;

function validateLine(form: LineForm) {
  const errors: Record<string, string[]> = {};
  if (!form.description.trim())
    errors.description = ["Description is required."];
  if (!decimal.test(form.quantity) || Number(form.quantity) <= 0)
    errors.quantity = ["Quantity must be a positive number."];
  if (!decimal.test(form.unit_price))
    errors.unit_price = ["Unit price must be zero or a positive number."];
  if (form.discount_amount && !decimal.test(form.discount_amount))
    errors.discount_amount = ["Discount must be zero or a positive number."];
  if (form.tax_rate && !decimal.test(form.tax_rate))
    errors.tax_rate = ["Tax rate must be zero or a positive number."];
  if (!form.revenue_account)
    errors.revenue_account = ["Revenue account is required."];
  return errors;
}

function toPayload(form: LineForm) {
  return {
    description: form.description.trim(),
    quantity: form.quantity,
    unit: form.unit || "SERVICE",
    unit_price: form.unit_price,
    discount_amount: form.discount_amount || "0.00",
    tax_rate: form.tax_rate || "0.00",
    revenue_account: form.revenue_account,
    contract_service: form.contract_service || null,
    site: form.site || null,
    billing_rule: form.billing_rule || null,
  };
}

export function InvoiceLineEditor({
  invoice,
  onChanged,
  onConflict,
}: {
  invoice: InvoiceDetail;
  onChanged: (invoice: InvoiceDetail) => void;
  onConflict: () => Promise<void>;
}) {
  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [accountsError, setAccountsError] = useState("");
  const [allContractServices, setAllContractServices] = useState<
    ContractServiceOption[]
  >([]);
  const [allSites, setAllSites] = useState<SiteOption[]>([]);
  const [billingRules, setBillingRules] = useState<BillingRuleOption[]>([]);
  const [form, setForm] = useState<LineForm>(emptyForm);
  const [editingLineId, setEditingLineId] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [nonFieldError, setNonFieldError] = useState<string>();
  const [saving, setSaving] = useState(false);
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(
    null,
  );
  const [pendingLineId, setPendingLineId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    listAccounts()
      .then((list) => {
        if (active) setAccounts(list);
      })
      .catch(() => {
        if (active)
          setAccountsError(
            "Revenue accounts are not available with your current permissions.",
          );
      });
    listBillingRules()
      .then((list) => {
        if (active) setBillingRules(list);
      })
      .catch(() => undefined);
    listContractServices()
      .then((list) => {
        if (active) setAllContractServices(list);
      })
      .catch(() => undefined);
    listSites()
      .then((list) => {
        if (active) setAllSites(list);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const contractServices = invoice.contract
    ? allContractServices.filter(
        (service) => service.contract === invoice.contract,
      )
    : [];
  const sites = invoice.contract
    ? allSites.filter((site) => site.contract === invoice.contract)
    : [];

  function set(key: keyof LineForm, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function startEdit(line: InvoiceLine) {
    setEditingLineId(line.id);
    setErrors({});
    setNonFieldError(undefined);
    setForm({
      description: line.description,
      quantity: line.quantity,
      unit: line.unit,
      unit_price: line.unit_price,
      discount_amount: line.discount_amount,
      tax_rate: "0.00",
      revenue_account: line.revenue_account,
      contract_service: line.contract_service ?? "",
      site: line.site ?? "",
      billing_rule: line.billing_rule ?? "",
    });
  }

  function cancelEdit() {
    setEditingLineId(null);
    setForm(emptyForm);
    setErrors({});
    setNonFieldError(undefined);
  }

  async function refreshInvoice() {
    const refreshed = await getInvoice(invoice.id);
    onChanged(refreshed);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    const validation = validateLine(form);
    if (Object.keys(validation).length) {
      setErrors(validation);
      return;
    }
    setSaving(true);
    setErrors({});
    setNonFieldError(undefined);
    try {
      if (editingLineId) {
        await updateInvoiceLine(invoice.id, editingLineId, toPayload(form));
      } else {
        await addInvoiceLine(invoice.id, toPayload(form));
      }
      await refreshInvoice();
      cancelEdit();
    } catch (caught) {
      if (caught instanceof ApiError) {
        setErrors(caught.fieldErrors);
        setNonFieldError(caught.message);
      } else {
        setNonFieldError("The invoice line could not be saved.");
      }
      await onConflict();
    } finally {
      setSaving(false);
    }
  }

  async function removeLine(lineId: string) {
    setPendingLineId(lineId);
    try {
      await deleteInvoiceLine(invoice.id, lineId);
      await refreshInvoice();
    } catch (caught) {
      setNonFieldError(
        caught instanceof ApiError
          ? caught.message
          : "The invoice line could not be removed.",
      );
      await onConflict();
    } finally {
      setPendingLineId(null);
      setConfirmingDeleteId(null);
    }
  }

  const canAddLine = accounts.length > 0 || Boolean(form.revenue_account);

  return (
    <div className="line-editor">
      {invoice.lines.length ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Description</th>
                <th>Quantity</th>
                <th>Unit price</th>
                <th>Line total</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {invoice.lines.map((line) => (
                <tr key={line.id}>
                  <td>{line.line_number}</td>
                  <td>{line.description}</td>
                  <td>{line.quantity}</td>
                  <td>{formatMoney(line.unit_price, invoice.currency)}</td>
                  <td>{formatMoney(line.line_total, invoice.currency)}</td>
                  <td>
                    {confirmingDeleteId === line.id ? (
                      <span className="filter-actions">
                        <span>Remove this invoice line?</span>
                        <Button
                          type="button"
                          disabled={pendingLineId === line.id}
                          onClick={() => removeLine(line.id)}
                        >
                          {pendingLineId === line.id
                            ? "Removing…"
                            : "Confirm remove"}
                        </Button>
                        <Button
                          type="button"
                          className="button-secondary"
                          disabled={pendingLineId === line.id}
                          onClick={() => setConfirmingDeleteId(null)}
                        >
                          Cancel
                        </Button>
                      </span>
                    ) : (
                      <span className="filter-actions">
                        <Button
                          type="button"
                          className="button-secondary"
                          onClick={() => startEdit(line)}
                        >
                          Edit
                        </Button>
                        <Button
                          type="button"
                          className="button-secondary"
                          onClick={() => setConfirmingDeleteId(line.id)}
                        >
                          Remove
                        </Button>
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>No line items yet.</p>
      )}

      {accountsError ? <p className="field-error">{accountsError}</p> : null}

      <form
        className="invoice-form line-form"
        onSubmit={submit}
        aria-label={editingLineId ? "Edit invoice line" : "Add invoice line"}
      >
        <h3>{editingLineId ? "Edit line" : "Add line"}</h3>
        <FormField
          id="line-description"
          label="Description"
          required
          value={form.description}
          onChange={(event) => set("description", event.target.value)}
          error={errors.description?.[0]}
          disabled={saving}
        />
        <FormField
          id="line-quantity"
          label="Quantity"
          required
          inputMode="decimal"
          value={form.quantity}
          onChange={(event) => set("quantity", event.target.value)}
          error={errors.quantity?.[0]}
          disabled={saving}
        />
        <FormField
          id="line-unit"
          label="Unit"
          value={form.unit}
          onChange={(event) => set("unit", event.target.value)}
          error={errors.unit?.[0]}
          disabled={saving}
        />
        <FormField
          id="line-unit-price"
          label="Unit price"
          required
          inputMode="decimal"
          value={form.unit_price}
          onChange={(event) => set("unit_price", event.target.value)}
          error={errors.unit_price?.[0]}
          disabled={saving}
        />
        <FormField
          id="line-discount"
          label="Discount amount"
          inputMode="decimal"
          value={form.discount_amount}
          onChange={(event) => set("discount_amount", event.target.value)}
          error={errors.discount_amount?.[0]}
          disabled={saving}
        />
        <FormField
          id="line-tax-rate"
          label="Tax rate (%)"
          inputMode="decimal"
          value={form.tax_rate}
          onChange={(event) => set("tax_rate", event.target.value)}
          error={errors.tax_rate?.[0]}
          disabled={saving}
        />
        <label className="form-field">
          <span>Revenue account</span>
          <select
            required
            value={form.revenue_account}
            onChange={(event) => set("revenue_account", event.target.value)}
            disabled={saving || accounts.length === 0}
          >
            <option value="">Select a revenue account</option>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.code} — {account.name}
              </option>
            ))}
          </select>
          {errors.revenue_account?.[0] ? (
            <span className="field-error">{errors.revenue_account[0]}</span>
          ) : null}
        </label>
        <label className="form-field">
          <span>Contract service</span>
          <select
            value={form.contract_service}
            onChange={(event) => set("contract_service", event.target.value)}
            disabled={saving || contractServices.length === 0}
          >
            <option value="">None</option>
            {contractServices.map((service) => (
              <option key={service.id} value={service.id}>
                {service.name}
              </option>
            ))}
          </select>
          {!invoice.contract ? (
            <span className="form-hint">
              Set a contract on the invoice to enable contract services.
            </span>
          ) : null}
        </label>
        <label className="form-field">
          <span>Site</span>
          <select
            value={form.site}
            onChange={(event) => set("site", event.target.value)}
            disabled={saving || sites.length === 0}
          >
            <option value="">None</option>
            {sites.map((site) => (
              <option key={site.id} value={site.id}>
                {site.site_code} — {site.name}
              </option>
            ))}
          </select>
        </label>
        <label className="form-field">
          <span>Billing rule</span>
          <select
            value={form.billing_rule}
            onChange={(event) => set("billing_rule", event.target.value)}
            disabled={saving || billingRules.length === 0}
          >
            <option value="">None</option>
            {billingRules.map((rule) => (
              <option key={rule.id} value={rule.id}>
                {rule.description}
              </option>
            ))}
          </select>
        </label>
        <FormError message={nonFieldError} />
        <div className="filter-actions">
          <Button type="submit" disabled={saving || !canAddLine}>
            {saving ? "Saving…" : editingLineId ? "Save line" : "Add line"}
          </Button>
          {editingLineId ? (
            <Button
              type="button"
              className="button-secondary"
              disabled={saving}
              onClick={cancelEdit}
            >
              Cancel
            </Button>
          ) : null}
        </div>
        {!canAddLine ? (
          <p className="field-error">
            No revenue accounts are available, so new lines cannot be added.
          </p>
        ) : null}
      </form>
    </div>
  );
}
