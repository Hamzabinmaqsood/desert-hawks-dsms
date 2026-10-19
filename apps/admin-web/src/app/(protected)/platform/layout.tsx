import type { Metadata } from "next";
import type { ReactNode } from "react";

import { PlatformRouteGuard } from "@/components/auth/platform-route-guard";
import { PLATFORM_DOCUMENT_TITLE } from "@/lib/product";

export const metadata: Metadata = { title: PLATFORM_DOCUMENT_TITLE };

export default function PlatformLayout({ children }: { children: ReactNode }) {
  return <PlatformRouteGuard>{children}</PlatformRouteGuard>;
}
