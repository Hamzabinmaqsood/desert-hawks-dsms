import type { ReactNode } from "react";
import { ModuleRouteGuard } from "@/components/auth/module-route-guard";
export default function Layout({ children }: { children: ReactNode }) {
  return <ModuleRouteGuard moduleId="people">{children}</ModuleRouteGuard>;
}
