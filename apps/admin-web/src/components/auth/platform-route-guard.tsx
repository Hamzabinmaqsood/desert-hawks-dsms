"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { ErrorState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";

export function PlatformRouteGuard({ children }: { children: ReactNode }) {
  const { platform_capabilities: access } = useAuth();
  if (!access.can_access_platform_admin)
    return (
      <section className="module-unavailable">
        <h1>Platform administration unavailable</h1>
        <ErrorState message="You do not have platform administration permission." />
        <Link className="button button-secondary" href="/dashboard">
          Back to Dashboard
        </Link>
      </section>
    );
  return children;
}
