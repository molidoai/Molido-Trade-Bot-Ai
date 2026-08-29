"use client";

import { useState } from "react";
import { getToken } from "@/lib/auth";
import { useApp } from "@/components/app/Providers";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export function TopBar() {
  const [busy, setBusy] = useState(false);
  const [master, setMaster] = useState(true);
  const [msg, setMsg] = useState("");
  const { setNavOpen, theme, toggle } = useApp();

  async function kill() {
    setBusy(true);
    setMsg("");
    try {
      const token = getToken();
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      const r = await fetch(`${API}/ops/master`, {
        method: "POST",
        headers,
        body: JSON.stringify({ enabled: false, actor: "dashboard-kill-switch" }),
      });
      if (r.status === 401 || r.status === 403) {
        setMsg("Kill Switch فقط با لاگین مالک");
        return;
      }
      if (!r.ok) {
        setMsg("خطا در Kill Switch");
        return;
      }
      setMaster(false);
      setMsg("ورود جدید قطع شد");
    } catch {
      setMsg("API در دسترس نیست");
    } finally {
      setBusy(false);
    }
  }

  return (
    <header className="sticky top-0 z-10 flex items-center justify-between gap-2 border-b border-[var(--line)] bg-[var(--panel)] px-3 py-3 backdrop-blur-xl md:px-6">
      <div className="flex min-w-0 items-center gap-2">
        <button
          type="button"
          className="rounded-lg border border-[var(--line)] px-2 py-1 text-sm md:hidden"
          onClick={() => setNavOpen(true)}
        >
          منو
        </button>
        <h1 className="truncate text-base font-semibold md:text-lg">Molido</h1>
        <span className="hidden rounded-full border border-amber-400/40 bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:text-amber-300 sm:inline">
          DEMO
        </span>
        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${
          master
            ? "border-emerald-400/30 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
            : "border-rose-400/30 bg-rose-500/15 text-rose-600 dark:text-rose-300"
        }`}>
          {master ? "روشن" : "قطع"}
        </span>
        {msg && <span className="hidden text-xs text-amber-600 dark:text-amber-300 sm:inline">{msg}</span>}
      </div>
      <div className="flex items-center gap-2 text-sm">
        <button type="button" onClick={toggle} className="rounded-lg border border-[var(--line)] px-2 py-1 text-xs">
          {theme === "dark" ? "روشن" : "تاریک"}
        </button>
        <button
          type="button"
          disabled={busy || !master}
          onClick={kill}
          className="rounded-lg border border-rose-500/40 bg-rose-600/15 px-2 py-1.5 text-xs text-rose-600 dark:text-rose-300 disabled:opacity-40 md:text-sm"
        >
          Kill
        </button>
      </div>
    </header>
  );
}
