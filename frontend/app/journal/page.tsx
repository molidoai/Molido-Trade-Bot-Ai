"use client";

import { useEffect, useState } from "react";
import { API, getToken } from "@/lib/auth";
import { TiltCard } from "@/components/ui/TiltCard";

type JournalEntry = {
  ts: string;
  event: string;
  symbol?: string;
  side?: string;
  reason?: string;
  r_multiple?: number;
  fill_price?: number;
  lot?: number;
  [key: string]: unknown;
};

type Stats = {
  n: number;
  win_rate: number;
  mean_r: number;
  sum_r: number;
};

const EVENT_LABEL: Record<string, { text: string; cls: string }> = {
  fill: { text: "پر شد", cls: "bg-emerald-400/20 text-emerald-300" },
  close: { text: "بسته شد", cls: "bg-cyan-400/20 text-cyan-300" },
  exit: { text: "خروج", cls: "bg-cyan-400/20 text-cyan-300" },
  flatten: { text: "flatten", cls: "bg-amber-400/20 text-amber-300" },
  veto: { text: "وتو", cls: "bg-rose-400/20 text-rose-300" },
  skip: { text: "رد شد", cls: "bg-slate-400/20 text-slate-300" },
  accept: { text: "پذیرفته شد", cls: "bg-emerald-400/20 text-emerald-300" },
  open_mark: { text: "به‌روزرسانی", cls: "bg-slate-400/20 text-slate-400" },
};

export default function JournalPage() {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    let alive = true;

    async function load() {
      const token = getToken();
      if (!token) {
        setMsg("برای دیدن ژورنال اول وارد شو");
        return;
      }
      try {
        const r = await fetch(`${API}/journal/recent`, {
          headers: { Authorization: `Bearer ${token}` },
          cache: "no-store",
        });
        if (!alive) return;
        if (!r.ok) {
          setMsg(r.status === 401 ? "نشست منقضی است" : "خطا در خواندن ژورنال");
          return;
        }
        const data = await r.json();
        if (!alive) return;
        const list: JournalEntry[] = data.entries || [];
        setEntries(list);
        setStats(data.stats || null);
        setMsg(list.length ? "" : "ژورنال معاملات هنوز خالی است — هنوز چرخه‌ای اجرا نشده");
      } catch {
        if (alive) setMsg("API در دسترس نیست");
      }
    }

    void load();
    const id = setInterval(load, 15000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="space-y-6">
      <h2 className="aurora text-3xl font-black">ژورنال</h2>

      {stats ? (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <TiltCard>
            <p className="text-xs text-slate-400">معاملات بسته‌شده</p>
            <p className="mt-2 text-2xl font-semibold">{stats.n}</p>
          </TiltCard>
          <TiltCard>
            <p className="text-xs text-slate-400">نرخ برد</p>
            <p className="mt-2 text-2xl font-semibold">{(stats.win_rate * 100).toFixed(1)}٪</p>
          </TiltCard>
          <TiltCard>
            <p className="text-xs text-slate-400">میانگین R</p>
            <p className={`mt-2 text-2xl font-semibold ${stats.mean_r >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
              {stats.mean_r.toFixed(2)}R
            </p>
          </TiltCard>
          <TiltCard>
            <p className="text-xs text-slate-400">مجموع R</p>
            <p className={`mt-2 text-2xl font-semibold ${stats.sum_r >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
              {stats.sum_r.toFixed(2)}R
            </p>
          </TiltCard>
        </div>
      ) : null}

      <TiltCard>
        {msg ? <p className="mb-3 text-sm text-slate-400">{msg}</p> : null}
        <div className="max-h-[32rem] space-y-2 overflow-y-auto">
          {entries.map((e, i) => {
            const label = EVENT_LABEL[e.event] || { text: e.event, cls: "bg-slate-400/20 text-slate-300" };
            return (
              <div key={i} className="rounded-xl border border-white/10 bg-black/20 p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs ${label.cls}`}>{label.text}</span>
                    {e.symbol ? <span className="font-semibold">{e.symbol}</span> : null}
                    {e.side ? <span className="text-slate-400">{e.side}</span> : null}
                  </div>
                  <span className="text-xs text-slate-500">{new Date(e.ts).toLocaleString("fa-IR", { timeZone: "Asia/Tehran" })}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-400">
                  {e.r_multiple != null ? <span>R={Number(e.r_multiple).toFixed(2)}</span> : null}
                  {e.lot != null ? <span>lot={e.lot}</span> : null}
                  {e.fill_price != null ? <span>@{e.fill_price}</span> : null}
                  {e.reason ? <span className="truncate">{e.reason}</span> : null}
                </div>
              </div>
            );
          })}
        </div>
      </TiltCard>
    </div>
  );
}
