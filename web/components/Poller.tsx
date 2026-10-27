"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
export default function Poller() {
  const r = useRouter();
  useEffect(() => { const t = setInterval(() => r.refresh(), 3000); return () => clearInterval(t); }, [r]);
  return null;
}
