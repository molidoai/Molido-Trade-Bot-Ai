"use client";

import { useEffect, useState } from "react";
import { API, getToken } from "@/lib/auth";
import { TiltCard } from "@/components/ui/TiltCard";

type TVAlert = {
  ts: number | null;
  body: unknown;
};

function fmtTime(ts: number | null): string {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString("fa-IR", { timeZone: "Asia/Tehran" });
}

function fmtBody(body: unknown): string {
  if (typeof body === "string") return body;
  try {
    return JSON.stringify(body, null, 2);
  } catch {
    return String(body);
  }
}

export function TVAlertsPanel() {
  const [alerts, setAlerts] = useState<TVAlert[]>([]);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    let alive = true;

    async function load() {
      const token = getToken();
      if (!token) {
        setMsg("برای دیدن آلرت‌های TradingView اول وارد شو");
        return;
      }
      try {
        const r = await fetch(`${API}/tv-alerts/recent`, {
          headers: { Authorization: `Bearer ${token}` },
          cache: "no-store",
        });
        if (!alive) return;
        if (!r.ok) {
          setMsg(r.status === 401 ? "نشست منقضی است" : "خطا در خواندن آلرت‌ها");
          return;
        }
        const data = await r.json();
        if (!alive) return;
        setAlerts(data.alerts || []);
        setMsg(data.alerts?.length ? "" : "هنوز هیچ آلرتی از TradingView دریافت نشده");
      } catch {
        if (alive) setMsg("API در دسترس نیست");
      }
    }

    void load();
    const id = setInterval(load, 10000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  return (
    <TiltCard>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-medium">آلرت‌های TradingView</h2>
        <span className="rounded-full bg-slate-400/20 px-2 py-0.5 text-xs text-slate-300">فقط نمایشی</span>
      </div>
      {msg ? <p className="text-sm text-slate-400">{msg}</p> : null}
      <div className="max-h-80 space-y-2 overflow-y-auto">
        {alerts.map((a, i) => (
          <div key={i} className="rounded-xl border border-white/10 bg-black/20 p-3">
            <div className="mb-1 text-xs text-slate-500">{fmtTime(a.ts)}</div>
            <pre className="whitespace-pre-wrap break-words text-xs text-slate-300">{fmtBody(a.body)}</pre>
          </div>
        ))}
      </div>
    </TiltCard>
  );
}
