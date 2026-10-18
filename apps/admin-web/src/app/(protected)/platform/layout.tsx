import type { ReactNode } from "react";

import { PlatformRouteGuard } from "@/components/auth/platform-route-guard";

export default function PlatformLayout({ children }: { children: ReactNode }) {
  return <PlatformRouteGuard>{children}</PlatformRouteGuard>;
}
