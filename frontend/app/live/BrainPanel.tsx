"use client";

import { useEffect, useState } from "react";
import { API, getToken } from "@/lib/auth";
import { TiltCard } from "@/components/ui/TiltCard";

type BrainVote = { name: string; allow: boolean; size_mult: number };

type Decision = {
  ts: string;
  symbol: string;
  side: string | null;
  allow: boolean;
  size_mult: number | null;
  p_win: number | null;
  expected_r: number | null;
  skipped_reason: string | null;
  brains: BrainVote[];
};

const BRAIN_LABEL: Record<string, string> = {
  setup: "مغز ۱ · Setup",
  edge: "مغز ۲ · Edge",
  survival: "مغز ۳ · Survival",
};

function VoteBadge({ vote }: { vote: BrainVote }) {
  const ok = vote.allow && vote.size_mult > 0;
  const color = !ok
    ? "bg-rose-400/20 text-rose-300"
    : vote.size_mult >= 1
      ? "bg-emerald-400/20 text-emerald-300"
      : "bg-amber-400/20 text-amber-300";
  return (
    <div className={`rounded-xl px-3 py-2 text-xs ${color}`}>
      <div className="font-medium">{BRAIN_LABEL[vote.name] || vote.name}</div>
      <div className="mt-0.5 opacity-80">{ok ? `size ×${vote.size_mult}` : "وتو"}</div>
    </div>
  );
}

export function BrainPanel() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    let alive = true;

    async function load() {
      const token = getToken();
      if (!token) {
        setMsg("برای دیدن تصمیم مغزها اول وارد شو");
        return;
      }
      try {
        const r = await fetch(`${API}/brain/decisions`, {
          headers: { Authorization: `Bearer ${token}` },
          cache: "no-store",
        });
        if (!alive) return;
        if (!r.ok) {
          setMsg(r.status === 401 ? "نشست منقضی است. دوباره وارد شو." : "خطا در خواندن تصمیم‌ها");
          return;
        }
        const data = await r.json();
        if (!alive) return;
        const list: Decision[] = data.decisions || [];
        setDecisions(list);
        setUpdatedAt(data.updated_at || null);
        setMsg(list.length ? "" : "هنوز تصمیمی ثبت نشده — موتور باید یک چرخه کامل بزند");
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

  return (
    <TiltCard>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-medium">مغز ۱ · ۲ · ۳ — آخرین تصمیم‌ها</h2>
        {updatedAt ? (
          <span className="text-xs text-slate-500">
            {new Date(updatedAt).toLocaleTimeString("fa-IR", { timeZone: "Asia/Tehran" })}
          </span>
        ) : null}
      </div>
      {msg ? <p className="text-sm text-slate-400">{msg}</p> : null}
      <div className="space-y-3">
        {decisions.map((d, i) => (
          <div key={`${d.ts}-${d.symbol}-${i}`} className="rounded-2xl border border-white/10 bg-black/20 p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-sm">
              <div className="flex items-center gap-2">
                <span className="font-semibold">{d.symbol}</span>
                {d.side ? <span className="text-slate-400">{d.side}</span> : null}
                <span
                  className={`rounded-full px-2 py-0.5 text-xs ${
                    d.allow ? "bg-emerald-400/20 text-emerald-300" : "bg-rose-400/20 text-rose-300"
                  }`}
                >
                  {d.allow ? "اجازه" : "وتو"}
                </span>
              </div>
              <div className="text-xs text-slate-400">
                {d.p_win != null ? `P(win)=${d.p_win.toFixed(2)}` : null}
                {d.expected_r != null ? ` · EV=${d.expected_r.toFixed(2)}R` : null}
                {d.size_mult != null ? ` · size×${d.size_mult}` : null}
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {d.brains.map((v) => (
                <VoteBadge key={v.name} vote={v} />
              ))}
            </div>
            {d.skipped_reason ? <p className="mt-2 text-xs text-slate-500">{d.skipped_reason}</p> : null}
          </div>
        ))}
      </div>
    </TiltCard>
  );
}
