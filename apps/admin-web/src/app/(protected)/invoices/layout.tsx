import type { ReactNode } from "react";

import { ModuleRouteGuard } from "@/components/auth/module-route-guard";

export default function InvoiceLayout({ children }: { children: ReactNode }) {
  return (
    <ModuleRouteGuard moduleId="billing_receivables">
      {children}
    </ModuleRouteGuard>
  );
}
