"use client";

/**
 * Live account KPIs for the overview page.
 *
 * These six cards used to be hardcoded strings on the server-rendered page
 * ("—", "منتظر MT5", "$۰.۰۰", "۰٪", "۰"), so they never showed anything the
 * engine reported -- "منتظر MT5" was fixed text, not a real connection state,
 * and stayed put even with a healthy bridge and a funded account.
 *
 * They have to be a client component: /portfolio/status requires auth and the
 * session token lives in sessionStorage, which a Server Component cannot read.
 */

import { useEffect, useState } from "react";
import { API, getToken } from "@/lib/auth";

type Totals = {
  equity?: number | null;
  balance?: number | null;
  unrealized_pnl?: number | null;
  open_positions?: number | null;
};

type Status = {
  balance?: number | null;
  equity?: number | null;
  unrealized_pnl?: number | null;
  open_positions?: number | null;
  drawdown_pct?: number | null;
  as_of?: string | null;
  totals?: Totals | null;
};

const FA = "fa-IR";

function money(v: number | null | undefined): string | null {
  if (typeof v !== "number" || !Number.isFinite(v)) return null;
  return "$" + v.toLocaleString(FA, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function percent(v: number | null | undefined): string | null {
  if (typeof v !== "number" || !Number.isFinite(v)) return null;
  // The engine writes drawdown_pct as a percentage already (0.00 = flat).
  return v.toLocaleString(FA, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + "٪";
}

function count(v: number | null | undefined): string | null {
  if (typeof v !== "number" || !Number.isFinite(v)) return null;
  return v.toLocaleString(FA);
}

function Kpi({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string | null;
  sub?: string;
  accent?: string;
}) {
  // A dash means "not loaded yet", and must never be dressed up as a real zero.
  const missing = value === null;
  return (
    <div className="glass rounded-2xl p-4">
      <div className="mb-1 text-xs text-slate-400">{label}</div>
      <div className={`text-xl font-semibold ${missing ? "text-slate-500" : accent || ""}`}>
        {missing ? "—" : value}
      </div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

export function LiveKpis({ mode }: { mode: string }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [note, setNote] = useState("در حال خواندن…");

  useEffect(() => {
    let alive = true;

    async function load() {
      const token = getToken();
      if (!token) {
        if (alive) setNote("برای دیدن موجودی وارد شو");
        return;
      }
      try {
        const r = await fetch(`${API}/portfolio/status`, {
          headers: { Authorization: `Bearer ${token}` },
          cache: "no-store",
        });
        if (!alive) return;
        if (!r.ok) {
          setNote(r.status === 401 ? "نشست منقضی است. دوباره وارد شو." : "خطا در خواندن حساب");
          return;
        }
        const data: Status = await r.json();
        if (!alive) return;
        setStatus(data);
        setNote(data.as_of ? "" : "موتور هنوز عکس‌برداری نکرده");
      } catch {
        if (alive) setNote("API در دسترس نیست");
      }
    }

    void load();
    const id = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  // Prefer the cross-account totals when the engine runs more than one account.
  const t = status?.totals || null;
  const balance = t?.balance ?? status?.balance;
  const equity = t?.equity ?? status?.equity;
  const pnl = t?.unrealized_pnl ?? status?.unrealized_pnl;
  const open = t?.open_positions ?? status?.open_positions;

  const pnlAccent =
    typeof pnl === "number" && pnl !== 0
      ? pnl > 0
        ? "text-emerald-300"
        : "text-rose-300"
      : undefined;

  const asOf = status?.as_of
    ? new Date(status.as_of).toLocaleTimeString(FA, {
        timeZone: "Asia/Tehran",
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
      <Kpi label="موجودی" value={money(balance)} sub={asOf ? `به‌روز ${asOf}` : note || undefined} />
      <Kpi label="اکوئیتی" value={money(equity)} accent="text-cyan-300" />
      <Kpi label="PnL باز" value={money(pnl)} accent={pnlAccent} />
      <Kpi label="دراودان" value={percent(status?.drawdown_pct)} />
      <Kpi label="پوزیشن باز" value={count(open)} />
      <Kpi
        label="حالت حساب"
        value={mode}
        accent={mode === "REAL" ? "text-rose-300" : "text-emerald-300"}
      />
    </div>
  );
}
