import "./globals.css";
import Link from "next/link";
import type { ReactNode } from "react";
export const metadata = { title: "ProofFrame workbench" };
export default function Root({ children }: { children: ReactNode }) {
  return (
    <html lang="en"><body>
      <nav className="nav"><b>ProofFrame</b><Link href="/">Runs</Link><Link href="/upload">New verification</Link></nav>
      <main>{children}</main>
    </body></html>
  );
}
