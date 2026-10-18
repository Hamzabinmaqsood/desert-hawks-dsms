import type { ReactNode } from "react";

import { ModuleRouteGuard } from "@/components/auth/module-route-guard";

export default function VendorLayout({ children }: { children: ReactNode }) {
  return (
    <ModuleRouteGuard moduleId="procurement_payables">
      {children}
    </ModuleRouteGuard>
  );
}
