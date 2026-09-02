import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { AuthProvider } from "@/features/auth/auth-context";
import { loadSession } from "@/lib/auth/session";

export default async function ProtectedLayout({
  children,
}: {
  children: ReactNode;
}) {
  const result = await loadSession(await cookies());
  if (result.status !== 200 || !result.session) redirect("/login");
  return (
    <AuthProvider session={result.session}>
      <AppShell session={result.session}>{children}</AppShell>
    </AuthProvider>
  );
}
