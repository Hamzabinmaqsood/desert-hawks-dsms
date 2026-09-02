export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="state-card" role="status">
      {label}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="state-card state-error" role="alert">
      {message}
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return <div className="state-card">{message}</div>;
}
