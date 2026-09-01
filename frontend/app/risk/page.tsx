"use client";

import { useEffect, useState } from "react";
import { API, getToken } from "@/lib/auth";
import { TiltCard } from "@/components/ui/TiltCard";

type RiskSettings = {
  default_risk_per_trade: number;
  max_daily_loss: number;
  max_drawdown: number;
  max_open_positions: number;
};

export default function RiskPage() {
  const [settings, setSettings] = useState<RiskSettings | null>(null);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    let alive = true;

    async function load() {
      const token = getToken();
      if (!token) {
        setMsg("برای دیدن تنظیمات ریسک اول وارد شو");
        return;
      }
      try {
        const r = await fetch(`${API}/settings`, {
          headers: { Authorization: `Bearer ${token}` },
          cache: "no-store",
        });
        if (!alive) return;
        if (!r.ok) {
          setMsg(r.status === 401 ? "نشست منقضی است" : "خطا در خواندن تنظیمات");
          return;
        }
        const data = await r.json();
        if (!alive) return;
        setSettings(data);
      } catch {
        if (alive) setMsg("API در دسترس نیست");
      }
    }

    void load();
    const id = setInterval(load, 20000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="space-y-6">
      <h2 className="aurora text-3xl font-black">ریسک</h2>
      {msg ? <p className="text-sm text-slate-400">{msg}</p> : null}
      <div className="grid gap-4 md:grid-cols-2">
        <TiltCard>
          <p className="text-xs text-slate-400">ریسک هر معامله</p>
          <p className="mt-2 text-2xl font-semibold">
            {settings ? `${(settings.default_risk_per_trade * 100).toFixed(2)}٪` : "—"}
          </p>
        </TiltCard>
        <TiltCard>
          <p className="text-xs text-slate-400">سقف ضرر روزانه</p>
          <p className="mt-2 text-2xl font-semibold">
            {settings ? `${(settings.max_daily_loss * 100).toFixed(1)}٪` : "—"}
          </p>
        </TiltCard>
        <TiltCard>
          <p className="text-xs text-slate-400">حداکثر دراودان</p>
          <p className="mt-2 text-2xl font-semibold">
            {settings ? `${(settings.max_drawdown * 100).toFixed(1)}٪` : "—"}
          </p>
        </TiltCard>
        <TiltCard>
          <p className="text-xs text-slate-400">حداکثر پوزیشن باز</p>
          <p className="mt-2 text-2xl font-semibold">{settings ? settings.max_open_positions : "—"}</p>
        </TiltCard>
      </div>
      <p className="text-xs text-slate-500">
        این مقدارها مستقیم از تنظیمات سرور خونده می‌شن (صفحه‌ی تنظیمات) — تغییرشون از همون‌جا انجام می‌شه.
      </p>
    </div>
  );
}
