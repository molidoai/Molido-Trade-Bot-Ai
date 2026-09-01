"use client";

import { useEffect, useState } from "react";
import { API, getToken } from "@/lib/auth";
import { TiltCard } from "@/components/ui/TiltCard";

type Position = {
  ticket: string;
  symbol: string;
  side: string;
  volume: number;
  entry_price: number;
  current_price: number;
  stop_loss: number | null;
  take_profit: number | null;
  unrealized_pnl: number;
  swap: number;
  opened_at: string | null;
  strategy: string | null;
};

type Status = {
  as_of: string | null;
  equity?: number;
  balance?: number;
  unrealized_pnl?: number;
  open_positions?: number;
  positions: Position[];
  note?: string;
};

function money(v: number | undefined): string {
  if (v == null) return "—";
  return `$${v.toFixed(2)}`;
}

function pnlClass(v: number): string {
  if (v > 0) return "text-emerald-300";
  if (v < 0) return "text-rose-300";
  return "text-slate-300";
}

export default function PositionsPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    let alive = true;

    async function load() {
      const token = getToken();
      if (!token) {
        setMsg("برای دیدن پوزیشن‌ها اول وارد شو");
        return;
      }
      try {
        const r = await fetch(`${API}/portfolio/status`, {
          headers: { Authorization: `Bearer ${token}` },
          cache: "no-store",
        });
        if (!alive) return;
        if (!r.ok) {
          setMsg(r.status === 401 ? "نشست منقضی است" : "خطا در خواندن پوزیشن‌ها");
          return;
        }
        const data: Status = await r.json();
        if (!alive) return;
        setStatus(data);
        if (data.note) setMsg("موتور هنوز snapshot ننوشته — یک چرخه صبر کن");
        else if (!data.positions?.length) setMsg("هیچ پوزیشن بازی وجود ندارد");
        else setMsg("");
      } catch {
        if (alive) setMsg("API در دسترس نیست");
      }
    }

    void load();
    const id = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const positions = status?.positions || [];

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <h2 className="aurora text-3xl font-black">پوزیشن‌ها</h2>
        {status?.as_of ? (
          <span className="text-xs text-slate-500">
            {new Date(status.as_of).toLocaleTimeString("fa-IR", { timeZone: "Asia/Tehran" })}
          </span>
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <TiltCard>
          <p className="text-xs text-slate-400">اکوئیتی</p>
          <p className="mt-2 text-xl font-semibold">{money(status?.equity)}</p>
        </TiltCard>
        <TiltCard>
          <p className="text-xs text-slate-400">موجودی</p>
          <p className="mt-2 text-xl font-semibold">{money(status?.balance)}</p>
        </TiltCard>
        <TiltCard>
          <p className="text-xs text-slate-400">سود/زیان باز</p>
          <p className={`mt-2 text-xl font-semibold ${pnlClass(status?.unrealized_pnl ?? 0)}`}>
            {money(status?.unrealized_pnl)}
          </p>
        </TiltCard>
        <TiltCard>
          <p className="text-xs text-slate-400">پوزیشن باز</p>
          <p className="mt-2 text-xl font-semibold">{status?.open_positions ?? 0}</p>
        </TiltCard>
      </div>

      <TiltCard>
        {msg ? <p className="mb-3 text-sm text-slate-400">{msg}</p> : null}
        <div className="space-y-2">
          {positions.map((p) => (
            <div key={p.ticket} className="rounded-xl border border-white/10 bg-black/20 p-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-semibold">{p.symbol}</span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${
                      p.side.toUpperCase() === "BUY"
                        ? "bg-emerald-400/20 text-emerald-300"
                        : "bg-rose-400/20 text-rose-300"
                    }`}
                  >
                    {p.side}
                  </span>
                  <span className="text-xs text-slate-400">{p.volume} لات</span>
                </div>
                <span className={`font-semibold ${pnlClass(p.unrealized_pnl)}`}>{money(p.unrealized_pnl)}</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
                <span>ورود: {p.entry_price}</span>
                <span>فعلی: {p.current_price}</span>
                <span>SL: {p.stop_loss ?? "—"}</span>
                <span>TP: {p.take_profit ?? "—"}</span>
                {p.swap ? <span>swap: {p.swap.toFixed(2)}</span> : null}
                {p.strategy ? <span>{p.strategy}</span> : null}
              </div>
            </div>
          ))}
        </div>
      </TiltCard>
    </div>
  );
}
