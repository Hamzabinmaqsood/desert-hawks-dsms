import type { ReactNode } from "react";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="state-card" role="status" aria-live="polite">
      <strong>{label}</strong>
    </div>
  );
}

export function ErrorState({
  title = "Unable to load this content",
  message,
  action,
}: {
  title?: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <div className="state-card state-error" role="alert">
      <h2>{title}</h2>
      <p>{message}</p>
      {action ? <div className="state-actions">{action}</div> : null}
    </div>
  );
}

export function EmptyState({
  title = "Nothing here yet",
  description,
  message,
  action,
  guidance,
}: {
  title?: string;
  description?: string;
  message?: string;
  action?: ReactNode;
  guidance?: ReactNode;
}) {
  return (
    <section className="state-card state-empty">
      <h2>{title}</h2>
      <p>{description ?? message}</p>
      {action ? <div className="state-actions">{action}</div> : null}
      {guidance ? <div className="state-guidance">{guidance}</div> : null}
    </section>
  );
}
