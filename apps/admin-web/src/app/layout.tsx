import type { Metadata } from "next";
import type { ReactNode } from "react";

import { PRODUCT_DESCRIPTION, PRODUCT_NAME } from "@/lib/product";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: PRODUCT_NAME,
  description: PRODUCT_DESCRIPTION,
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
