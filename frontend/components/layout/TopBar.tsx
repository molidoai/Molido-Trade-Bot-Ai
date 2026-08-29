"use client";

import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export function TopBar() {
  const [busy, setBusy] = useState(false);
  const [master, setMaster] = useState(true);
  const [msg, setMsg] = useState("");

  async function kill() {
    setBusy(true);
    setMsg("");
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("molido_token") : null;
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      const r = await fetch(`${API}/ops/master`, {
        method: "POST",
        headers,
        body: JSON.stringify({ enabled: false, actor: "dashboard-kill-switch" }),
      });
      if (r.status === 401 || r.status === 403) {
        setMsg("Kill Switch فقط با لاگین ادمین کار می‌کند");
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
    <header className="sticky top-0 z-10 flex items-center justify-between border-b border-white/10 bg-slate-950/40 px-6 py-3 backdrop-blur-xl">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold">نمای کلی</h1>
        <span className="rounded-full border border-rose-400/40 bg-rose-500/15 px-2.5 py-0.5 text-xs font-bold text-rose-300">
          REAL
        </span>
        <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${
          master
            ? "border-emerald-400/30 bg-emerald-500/15 text-emerald-300"
            : "border-rose-400/30 bg-rose-500/15 text-rose-300"
        }`}>
          ربات: {master ? "روشن" : "قطع"}
        </span>
        {msg && <span className="text-xs text-amber-300">{msg}</span>}
      </div>
      <div className="flex items-center gap-4 text-sm">
        <div className="text-left">
          <div className="text-xs text-slate-400">Live pulse</div>
          <div className="font-semibold text-cyan-300">{master ? "فعال" : "paused"}</div>
        </div>
        <div className="h-8 w-px bg-white/10" />
        <button
          type="button"
          disabled={busy || !master}
          onClick={kill}
          className="rounded-lg border border-rose-500/40 bg-rose-600/20 px-3 py-1.5 text-sm text-rose-300 hover:bg-rose-600/35 disabled:opacity-40"
        >
          Kill Switch
        </button>
      </div>
    </header>
  );
}
