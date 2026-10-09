import type { Metadata } from "next";

import { LoginForm } from "@/components/auth/login-form";
import { BrandLogo } from "@/components/brand/brand-logo";

export const metadata: Metadata = { title: "Sign in | DSMS" };

export default function LoginPage() {
  return (
    <main className="auth-page">
      <section className="login-card" aria-labelledby="login-title">
        <div className="brand brand-login">
          <BrandLogo className="brand-logo-login" priority />
          <span>
            DSMS
            <br />
            <small>Security Management Platform</small>
          </span>
        </div>
        <h1 id="login-title">Welcome back</h1>
        <p>Sign in with your authorized employee account.</p>
        <LoginForm />
      </section>
    </main>
  );
}
