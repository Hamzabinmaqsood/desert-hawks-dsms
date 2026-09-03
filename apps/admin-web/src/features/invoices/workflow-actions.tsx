"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-context";
import { ApiError } from "@/lib/api/client";

import { approveInvoice, getInvoice, issueInvoice, submitInvoice } from "./api";
import type { InvoiceDetail } from "./types";

type WorkflowAction = "submit" | "approve" | "issue";

const TRANSITIONS: Record<
  WorkflowAction,
  {
    label: string;
    pendingLabel: string;
    prompt: string;
    confirmLabel: string;
    run: (id: string) => Promise<InvoiceDetail>;
    fallback: string;
  }
> = {
  submit: {
    label: "Submit for review",
    pendingLabel: "Submitting…",
    prompt:
      "Submit this invoice for review? You will not be able to edit it afterwards.",
    confirmLabel: "Confirm submit",
    run: submitInvoice,
    fallback: "The invoice could not be submitted for review.",
  },
  approve: {
    label: "Approve",
    pendingLabel: "Approving…",
    prompt: "Approve this invoice?",
    confirmLabel: "Confirm approve",
    run: approveInvoice,
    fallback: "The invoice could not be approved.",
  },
  issue: {
    label: "Issue invoice",
    pendingLabel: "Issuing…",
    prompt:
      "Issue this invoice? Issuing posts it to accounts receivable and generates the official PDF.",
    confirmLabel: "Confirm issue",
    run: issueInvoice,
    fallback: "The invoice could not be issued.",
  },
};

export function InvoiceWorkflowActions({
  invoice,
  onChanged,
}: {
  invoice: InvoiceDetail;
  onChanged: (invoice: InvoiceDetail) => void;
}) {
  const auth = useAuth();
  const [confirming, setConfirming] = useState<WorkflowAction | null>(null);
  const [pending, setPending] = useState<WorkflowAction | null>(null);
  const [error, setError] = useState("");

  const isDraft = invoice.status === "DRAFT";
  const canEdit = auth.can("billing.change_clientinvoice");
  const hasLines = invoice.lines.length > 0;
  // `generated_by` is the maker the backend compares against in
  // `_maker_checker`, and superusers are exempt there. Mirroring that rule
  // here is UX only — the backend re-checks it on every approval.
  const isOwnMaker =
    invoice.generated_by === auth.user.id && !auth.user.is_superuser;

  const available: WorkflowAction[] = [];
  if (isDraft && canEdit) available.push("submit");
  if (invoice.status === "UNDER_REVIEW" && auth.can("billing.approve_invoice"))
    available.push("approve");
  if (invoice.status === "APPROVED" && auth.can("billing.issue_invoice"))
    available.push("issue");

  async function run(action: WorkflowAction) {
    if (pending) return;
    setPending(action);
    setError("");
    try {
      onChanged(await TRANSITIONS[action].run(invoice.id));
      setConfirming(null);
    } catch (reason: unknown) {
      setError(
        reason instanceof ApiError && reason.message
          ? reason.message
          : TRANSITIONS[action].fallback,
      );
      setConfirming(null);
      // The rejection may mean another user already advanced the invoice, so
      // re-read authoritative state instead of leaving a stale action on screen.
      try {
        onChanged(await getInvoice(invoice.id));
      } catch {
        /* keep the transition error visible */
      }
    } finally {
      setPending(null);
    }
  }

  const blockedReason =
    isDraft && canEdit && !hasLines
      ? "Add at least one line before submitting."
      : available[0] === "approve" && isOwnMaker
        ? "This invoice requires approval by another authorized user."
        : "";

  // A transition error must survive the authoritative refresh that follows it:
  // once another user has advanced the invoice there may be no action left to
  // render, and dropping the section here would silently swallow the reason.
  if (!available.length && !(isDraft && canEdit) && !error) return null;

  return (
    <section className="workflow-actions" aria-label="Invoice workflow">
      <div className="filter-actions">
        {isDraft && canEdit ? (
          <Link
            className="button button-secondary"
            href={`/invoices/${invoice.id}/edit`}
          >
            Edit
          </Link>
        ) : null}
        {available.map((action) =>
          confirming === action ? (
            <span className="filter-actions" key={action}>
              <span>{TRANSITIONS[action].prompt}</span>
              <Button
                type="button"
                disabled={pending !== null}
                onClick={() => run(action)}
              >
                {pending === action
                  ? TRANSITIONS[action].pendingLabel
                  : TRANSITIONS[action].confirmLabel}
              </Button>
              <Button
                type="button"
                className="button-secondary"
                disabled={pending !== null}
                onClick={() => setConfirming(null)}
              >
                Cancel
              </Button>
            </span>
          ) : (
            <Button
              key={action}
              type="button"
              disabled={pending !== null || Boolean(blockedReason)}
              onClick={() => setConfirming(action)}
            >
              {TRANSITIONS[action].label}
            </Button>
          ),
        )}
      </div>
      {blockedReason ? <p className="field-hint">{blockedReason}</p> : null}
      {error ? (
        <p className="field-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
