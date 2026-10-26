import { ModuleRouteGuard } from "@/components/auth/module-route-guard";

export default function Layout({ children }: { children: React.ReactNode }) {
  return <ModuleRouteGuard moduleId="recruitment">{children}</ModuleRouteGuard>;
}
