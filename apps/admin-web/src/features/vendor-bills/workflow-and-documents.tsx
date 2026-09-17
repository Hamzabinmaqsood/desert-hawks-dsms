"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-context";
import { ApiError } from "@/lib/api/client";

import {
  listVendorBillAttachments,
  runVendorBillAction,
  uploadVendorBillAttachment,
} from "./api";
import type { VendorBill, VendorBillAttachment } from "./types";

type Action = "submit" | "approve" | "reject" | "post";

const copy: Record<Action, { label: string; prompt: string }> = {
  submit: {
    label: "Submit for review",
    prompt: "Submit this Vendor Bill for independent review?",
  },
  approve: { label: "Approve", prompt: "Approve this Vendor Bill?" },
  reject: { label: "Reject", prompt: "Reject this Vendor Bill?" },
  post: {
    label: "Post to accounts payable",
    prompt: "Post this approved Vendor Bill and create its accounting entries?",
  },
};

export function VendorBillWorkflow({
  bill,
  refresh,
}: {
  bill: VendorBill;
  refresh: () => Promise<void>;
}) {
  const auth = useAuth();
  const [confirming, setConfirming] = useState<Action | null>(null);
  const [pending, setPending] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const actions: Action[] = [];
  if (bill.status === "DRAFT" && auth.can("finance.change_vendorbill"))
    actions.push("submit");
  if (bill.status === "SUBMITTED" && auth.can("finance.approve_finance"))
    actions.push("approve", "reject");
  if (bill.status === "APPROVED" && auth.can("finance.post_journal"))
    actions.push("post");

  async function run(action: Action) {
    if (pending) return;
    setPending(true);
    setError("");
    try {
      await runVendorBillAction(bill.id, action, reason);
      await refresh();
      setConfirming(null);
      setReason("");
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "The workflow action failed.",
      );
      try {
        await refresh();
      } catch {
        // Keep the workflow error visible if the authoritative refresh fails.
      }
    } finally {
      setPending(false);
    }
  }

  if (!actions.length && !error) return null;
  return (
    <section className="workflow-actions" aria-label="Vendor Bill workflow">
      <div className="filter-actions">
        {actions.map((action) =>
          confirming === action ? (
            <span className="filter-actions" key={action}>
              <span>{copy[action].prompt}</span>
              {action === "reject" ? (
                <input
                  aria-label="Rejection reason"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder="Reason required"
                />
              ) : null}
              <Button
                disabled={pending || (action === "reject" && !reason.trim())}
                onClick={() => run(action)}
              >
                {pending
                  ? "Working..."
                  : `Confirm ${copy[action].label.toLowerCase()}`}
              </Button>
              <Button
                className="button-secondary"
                disabled={pending}
                onClick={() => setConfirming(null)}
              >
                Cancel
              </Button>
            </span>
          ) : (
            <Button
              key={action}
              disabled={pending}
              onClick={() => setConfirming(action)}
            >
              {copy[action].label}
            </Button>
          ),
        )}
      </div>
      {error ? (
        <p className="field-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}

export function VendorBillDocuments({ billId }: { billId: string }) {
  const auth = useAuth();
  const allowed = auth.can("finance.manage_finance_attachments");
  const [items, setItems] = useState<VendorBillAttachment[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const load = async () => setItems(await listVendorBillAttachments(billId));
  useEffect(() => {
    if (!allowed) return;
    let cancelled = false;
    listVendorBillAttachments(billId)
      .then((documents) => {
        if (!cancelled) setItems(documents);
      })
      .catch(() => {
        if (!cancelled) setError("Supporting documents could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, [allowed, billId]);
  if (!allowed) return null;
  async function upload(file?: File) {
    if (!file || pending) return;
    setPending(true);
    setError("");
    try {
      await uploadVendorBillAttachment(billId, file);
      await load();
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : "The document could not be uploaded.",
      );
    } finally {
      setPending(false);
    }
  }
  return (
    <section className="detail-card">
      <h2>Supporting Documents</h2>
      <label>
        <span>Upload PDF or image</span>
        <input
          aria-label="Supporting document"
          type="file"
          accept=".pdf,.jpg,.jpeg,.png"
          disabled={pending}
          onChange={(event) => upload(event.target.files?.[0])}
        />
      </label>
      {pending ? <p>Uploading...</p> : null}
      {error ? (
        <p className="field-error" role="alert">
          {error}
        </p>
      ) : null}
      {items.length ? (
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              <a
                href={`/api/vendor-bills/${encodeURIComponent(billId)}/attachments/${encodeURIComponent(item.id)}/download`}
              >
                {item.filename}
              </a>{" "}
              ({item.size} bytes)
            </li>
          ))}
        </ul>
      ) : (
        <p>No supporting documents uploaded.</p>
      )}
    </section>
  );
}
