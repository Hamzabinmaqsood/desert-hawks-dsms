"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { can, canAll, canAny } from "@/lib/auth/permissions";
import type { CompanyContext, SessionData } from "@/lib/auth/types";
import {
  hasAllModules as userHasAllModules,
  hasModule as userHasModule,
  type ModuleId,
} from "@/lib/modules";

export interface AuthContextValue extends SessionData {
  can: (permission: string) => boolean;
  canAny: (...permissions: string[]) => boolean;
  canAll: (...permissions: string[]) => boolean;
  hasModule: (moduleId: ModuleId) => boolean;
  hasAllModules: (...moduleIds: ModuleId[]) => boolean;
  switchingCompany: boolean;
  companySwitchError: string;
  switchCompany: (companyId: string) => Promise<boolean>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({
  session,
  children,
}: {
  session: SessionData;
  children: ReactNode;
}) {
  const router = useRouter();
  const [companyContextOverride, setCompanyContextOverride] = useState<{
    source: CompanyContext;
    value: CompanyContext;
  } | null>(null);
  const companyContext =
    companyContextOverride?.source === session.company_context
      ? companyContextOverride.value
      : session.company_context;
  const [switchingCompany, setSwitchingCompany] = useState(false);
  const [companySwitchError, setCompanySwitchError] = useState("");
  const superuser = session.user.is_superuser;

  useEffect(() => {
    const refreshCapabilities = () => router.refresh();
    window.addEventListener("dsms:module-not-enabled", refreshCapabilities);
    return () =>
      window.removeEventListener(
        "dsms:module-not-enabled",
        refreshCapabilities,
      );
  }, [router]);

  async function switchCompany(companyId: string) {
    if (switchingCompany) return false;
    setSwitchingCompany(true);
    setCompanySwitchError("");
    try {
      const response = await fetch("/api/auth/company-context", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company_id: companyId }),
      });
      const payload = (await response.json().catch(() => ({}))) as
        CompanyContext | { message?: string };
      if (!response.ok || !("companies" in payload)) {
        setCompanySwitchError(
          "message" in payload && payload.message
            ? payload.message
            : "Company switching failed.",
        );
        return false;
      }
      setCompanyContextOverride({
        source: session.company_context,
        value: payload,
      });
      router.replace("/dashboard");
      router.refresh();
      return true;
    } catch {
      setCompanySwitchError("Company switching is temporarily unavailable.");
      return false;
    } finally {
      setSwitchingCompany(false);
    }
  }
  const value: AuthContextValue = {
    ...session,
    company_context: companyContext,
    can: (permission) => can(session.permissions, permission, superuser),
    canAny: (...permissions) =>
      canAny(session.permissions, permissions, superuser),
    canAll: (...permissions) =>
      canAll(session.permissions, permissions, superuser),
    hasModule: (moduleId) =>
      userHasModule(companyContext.effective_modules, moduleId),
    hasAllModules: (...moduleIds) =>
      userHasAllModules(companyContext.effective_modules, ...moduleIds),
    switchingCompany,
    companySwitchError,
    switchCompany,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
