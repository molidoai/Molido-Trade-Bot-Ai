"use client";

import { useEffect, useState } from "react";
import { API, getToken } from "@/lib/auth";
import { TiltCard } from "@/components/ui/TiltCard";

type Status = {
  as_of: string | null;
  equity?: number;
  balance?: number;
  peak_equity?: number;
  drawdown_pct?: number;
  unrealized_pnl?: number;
  open_positions?: number;
  free_margin?: number;
  margin_level?: number | null;
  account_mode?: string;
  master_on?: boolean;
  session_note?: string;
  note?: string;
};

type JournalStats = {
  n: number;
  win_rate: number;
  mean_r: number;
  sum_r: number;
};

function money(v: number | undefined | null): string {
  if (v == null) return "—";
  return `$${v.toFixed(2)}`;
}

function pnlClass(v: number | undefined | null): string {
  if (v == null) return "text-slate-300";
  if (v > 0) return "text-emerald-300";
  if (v < 0) return "text-rose-300";
  return "text-slate-300";
}

export default function PerformancePage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [stats, setStats] = useState<JournalStats | null>(null);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    let alive = true;

    async function load() {
      const token = getToken();
      if (!token) {
        setMsg("برای دیدن عملکرد اول وارد شو");
        return;
      }
      try {
        const [statusRes, journalRes] = await Promise.all([
          fetch(`${API}/portfolio/status`, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" }),
          fetch(`${API}/journal/recent`, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store" }),
        ]);
        if (!alive) return;
        if (!statusRes.ok) {
          setMsg(statusRes.status === 401 ? "نشست منقضی است" : "خطا در خواندن وضعیت");
          return;
        }
        const statusData: Status = await statusRes.json();
        const journalData = journalRes.ok ? await journalRes.json() : null;
        if (!alive) return;
        setStatus(statusData);
        setStats(journalData?.stats || null);
        setMsg(statusData.note ? "موتور هنوز snapshot ننوشته — یک چرخه صبر کن" : "");
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

  // Growth vs the peak the engine has actually recorded -- not a claim about
  // starting capital, which the engine doesn't track.
  const equity = status?.equity;
  const balance = status?.balance;
  const openPnl = status?.unrealized_pnl;

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <h2 className="aurora text-3xl font-black">عملکرد</h2>
        {status?.as_of ? (
          <span className="text-xs text-slate-500">
            {new Date(status.as_of).toLocaleTimeString("fa-IR", { timeZone: "Asia/Tehran" })}
          </span>
        ) : null}
      </div>

      {msg ? <p className="text-sm text-slate-400">{msg}</p> : null}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <TiltCard>
          <p className="text-xs text-slate-400">اکوئیتی</p>
          <p className="mt-2 text-xl font-semibold">{money(equity)}</p>
        </TiltCard>
        <TiltCard>
          <p className="text-xs text-slate-400">موجودی</p>
          <p className="mt-2 text-xl font-semibold">{money(balance)}</p>
        </TiltCard>
        <TiltCard>
          <p className="text-xs text-slate-400">اوج اکوئیتی</p>
          <p className="mt-2 text-xl font-semibold">{money(status?.peak_equity)}</p>
        </TiltCard>
        <TiltCard>
          <p className="text-xs text-slate-400">دراودان</p>
          <p className={`mt-2 text-xl font-semibold ${(status?.drawdown_pct ?? 0) > 0 ? "text-amber-300" : ""}`}>
            {status?.drawdown_pct != null ? `${status.drawdown_pct.toFixed(2)}٪` : "—"}
          </p>
        </TiltCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <TiltCard>
          <h3 className="mb-3 font-medium">معاملات بسته‌شده</h3>
          {stats ? (
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                <div className="text-xs text-slate-400">تعداد</div>
                <div className="mt-1 text-lg font-semibold">{stats.n}</div>
              </div>
              <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                <div className="text-xs text-slate-400">نرخ برد</div>
                <div className="mt-1 text-lg font-semibold">{(stats.win_rate * 100).toFixed(1)}٪</div>
              </div>
              <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                <div className="text-xs text-slate-400">میانگین R</div>
                <div className={`mt-1 text-lg font-semibold ${pnlClass(stats.mean_r)}`}>{stats.mean_r.toFixed(2)}R</div>
              </div>
              <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                <div className="text-xs text-slate-400">مجموع R</div>
                <div className={`mt-1 text-lg font-semibold ${pnlClass(stats.sum_r)}`}>{stats.sum_r.toFixed(2)}R</div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-400">هنوز معامله‌ی بسته‌شده‌ای ثبت نشده</p>
          )}
        </TiltCard>

        <TiltCard>
          <h3 className="mb-3 font-medium">وضعیت فعلی</h3>
          <div className="space-y-2 text-sm">
            <Row label="سود/زیان باز" value={money(openPnl)} cls={pnlClass(openPnl)} />
            <Row label="پوزیشن باز" value={String(status?.open_positions ?? 0)} />
            <Row label="مارجین آزاد" value={money(status?.free_margin)} />
            <Row
              label="سطح مارجین"
              value={status?.margin_level != null ? `${status.margin_level.toFixed(0)}٪` : "—"}
            />
            <Row label="حالت حساب" value={status?.account_mode ?? "—"} />
            <Row label="مستر" value={status?.master_on ? "روشن" : "خاموش"} cls={status?.master_on ? "text-emerald-300" : "text-slate-400"} />
          </div>
          {status?.session_note ? (
            <p className="mt-3 text-xs text-slate-500">{status.session_note}</p>
          ) : null}
        </TiltCard>
      </div>
    </div>
  );
}

function Row({ label, value, cls }: { label: string; value: string; cls?: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-400">{label}</span>
      <span className={cls || "text-slate-200"}>{value}</span>
    </div>
  );
}
