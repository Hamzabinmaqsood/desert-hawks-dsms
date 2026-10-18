"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { MODULE_DISABLED_MESSAGE, type ModuleId } from "@/lib/modules";

export function ModuleRouteGuard({
  moduleId,
  children,
}: {
  moduleId: ModuleId;
  children: ReactNode;
}) {
  const auth = useAuth();
  if (auth.switchingCompany)
    return <LoadingState label="Refreshing Company capabilities..." />;
  if (!auth.hasModule(moduleId))
    return (
      <section
        className="module-unavailable"
        aria-labelledby="module-unavailable-title"
      >
        <h1 id="module-unavailable-title">Module unavailable</h1>
        <ErrorState message={MODULE_DISABLED_MESSAGE} />
        <p>
          Existing data is retained. Contact your platform administrator to
          change access.
        </p>
        <Link className="button button-secondary" href="/dashboard">
          Back to Dashboard
        </Link>
      </section>
    );
  return children;
}
