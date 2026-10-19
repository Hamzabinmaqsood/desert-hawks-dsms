import type { Metadata } from "next";

import { LoginForm } from "@/components/auth/login-form";
import { BrandLogo } from "@/components/brand/brand-logo";
import { PRODUCT_DESCRIPTION, PRODUCT_NAME } from "@/lib/product";

export const metadata: Metadata = { title: `Sign in | ${PRODUCT_NAME}` };

export default function LoginPage() {
  return (
    <main className="auth-page">
      <section className="login-card" aria-labelledby="login-title">
        <div className="brand brand-login">
          <BrandLogo className="brand-logo-login" priority />
          <span>
            {PRODUCT_NAME}
            <br />
            <small>{PRODUCT_DESCRIPTION}</small>
          </span>
        </div>
        <h1 id="login-title">Welcome back</h1>
        <p>Sign in with your authorized employee account.</p>
        <LoginForm />
      </section>
    </main>
  );
}
