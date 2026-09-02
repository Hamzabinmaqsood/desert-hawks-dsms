"use client";

import { createContext, useContext, type ReactNode } from "react";

import { can, canAll, canAny } from "@/lib/auth/permissions";
import type { SessionData } from "@/lib/auth/types";

interface AuthContextValue extends SessionData {
  can: (permission: string) => boolean;
  canAny: (...permissions: string[]) => boolean;
  canAll: (...permissions: string[]) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({
  session,
  children,
}: {
  session: SessionData;
  children: ReactNode;
}) {
  const superuser = session.user.is_superuser;
  const value: AuthContextValue = {
    ...session,
    can: (permission) => can(session.permissions, permission, superuser),
    canAny: (...permissions) =>
      canAny(session.permissions, permissions, superuser),
    canAll: (...permissions) =>
      canAll(session.permissions, permissions, superuser),
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
