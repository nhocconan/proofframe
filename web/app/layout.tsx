import "./globals.css";
import Link from "next/link";
import type { ReactNode } from "react";

export const metadata = { title: "ProofFrame — Verification Workbench" };

export default function Root({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="site-hdr">
          <div className="site-hdr-inner">
            <div className="brand-group">
              <Link href="/" className="brand">
                <span className="brand-mark" aria-hidden="true">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path
                      d="M2.25 5.25V2.75C2.25 2.47 2.47 2.25 2.75 2.25H5.25M10.75 2.25H13.25C13.53 2.25 13.75 2.47 13.75 2.75V5.25M13.75 10.75V13.25C13.75 13.53 13.53 13.75 13.25 13.75H10.75M5.25 13.75H2.75C2.47 13.75 2.25 13.53 2.25 13.25V10.75"
                      stroke="currentColor"
                      strokeWidth="1.6"
                      strokeLinecap="round"
                    />
                    <path
                      d="M5.5 8.15L7.2 9.85L10.65 6.25"
                      stroke="currentColor"
                      strokeWidth="1.75"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </span>
                <b className="brand-name">ProofFrame</b>
              </Link>
              <span className="brand-sep" aria-hidden="true" />
              <span className="brand-tag">Independent verification for generative video</span>
            </div>
            <nav className="site-nav" aria-label="Primary">
              <Link href="/" className="nav-item">Runs</Link>
              <Link href="/upload" className="nav-item btn-primary">New verification</Link>
            </nav>
          </div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
