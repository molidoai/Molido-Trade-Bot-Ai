"use client";

import { useEffect, useState } from "react";
import { TiltCard } from "@/components/ui/TiltCard";

type Parts = { weekday: number; hour: number; minute: number; second: number };

function getPartsInTZ(date: Date, timeZone: string): Parts {
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hour12: false,
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  const parts = fmt.formatToParts(date);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "0";
  // JS-style: Sun=0 .. Sat=6
  const weekdayMap: Record<string, number> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  return {
    weekday: weekdayMap[get("weekday")] ?? 0,
    hour: Number(get("hour")) % 24,
    minute: Number(get("minute")),
    second: Number(get("second")),
  };
}

function minuteOfDay(p: Parts): number {
  return p.hour * 60 + p.minute;
}

// Python's datetime.weekday(): Mon=0 .. Sun=6 (what packages/guards/molido_guards/sessions.py uses)
function pyWeekday(p: Parts): number {
  return (p.weekday + 6) % 7;
}

type SessionWindow = { key: string; nameFa: string; startMin: number; endMin: number; overnight: boolean };

// Mirrors FX_SESSIONS in packages/guards/molido_guards/sessions.py (America/New_York clock).
// Keep in sync with that file if session hours ever change there.
const SESSIONS: SessionWindow[] = [
  { key: "Tokyo", nameFa: "توکیو", startMin: 19 * 60, endMin: 4 * 60, overnight: true },
  { key: "London", nameFa: "لندن", startMin: 3 * 60, endMin: 12 * 60, overnight: false },
  { key: "NewYork", nameFa: "نیویورک", startMin: 8 * 60, endMin: 17 * 60, overnight: false },
  { key: "London_NY_Overlap", nameFa: "همپوشانی لندن/نیویورک", startMin: 8 * 60, endMin: 12 * 60, overnight: false },
];

function inWindow(m: number, w: SessionWindow): boolean {
  if (w.overnight) return m >= w.startMin || m <= w.endMin;
  return m >= w.startMin && m <= w.endMin;
}

function fmtHM(totalMin: number): string {
  const norm = ((totalMin % 1440) + 1440) % 1440;
  const h = Math.floor(norm / 60);
  const m = norm % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

type Status = {
  weekOpen: boolean;
  closedReason: string;
  allowEntries: boolean;
  entryReason: string;
  active: string[];
};

// Faithful port of SessionCalendar.is_fx_week_open / allow_new_entries.
// FX week runs Sunday 17:00 NY -> Friday 17:00 NY; these three checks are
// the complete closed window (fixed 2026-08-31: an earlier version of the
// Python source, and this port, had an extra `wd >= 5` catch-all that
// accidentally closed all of Sunday including *after* 17:00, silently
// skipping the Sydney/Tokyo open every week).
function marketStatus(nyP: Parts): Status {
  const wd = pyWeekday(nyP);
  const t = minuteOfDay(nyP);

  if (wd === 4 && t >= 17 * 60) {
    return { weekOpen: false, closedReason: "جمعه، بعد از ۱۷:۰۰ نیویورک — بسته", allowEntries: false, entryReason: "", active: [] };
  }
  if (wd === 5) {
    return { weekOpen: false, closedReason: "شنبه — فارکس بسته", allowEntries: false, entryReason: "", active: [] };
  }
  if (wd === 6 && t < 17 * 60) {
    return { weekOpen: false, closedReason: "یکشنبه، قبل از ۱۷:۰۰ نیویورک — بسته", allowEntries: false, entryReason: "", active: [] };
  }

  const active = SESSIONS.filter((w) => inWindow(t, w)).map((w) => w.key);

  if (wd === 0 && t < 8 * 60 + 30) {
    return { weekOpen: true, closedReason: "", allowEntries: false, entryReason: "دوشنبه، ۳۰ دقیقه‌ی اول نیویورک — فیلتر گپ", active };
  }
  if (wd === 3 && t >= 16 * 60) {
    return { weekOpen: true, closedReason: "", allowEntries: false, entryReason: "پنج‌شنبه بعد از ۱۶:۰۰ نیویورک — بدون ورود جدید (سواپ آخر هفته)", active };
  }
  if (wd === 4 && t >= 16 * 60) {
    return { weekOpen: true, closedReason: "", allowEntries: false, entryReason: "جمعه بعد از ۱۶:۰۰ نیویورک — بدون ورود جدید", active };
  }
  if (t >= 16 * 60 + 45 && t <= 17 * 60 + 15) {
    return { weekOpen: true, closedReason: "", allowEntries: false, entryReason: "پنجره‌ی rollover نیویورک", active };
  }
  if (active.length === 0) {
    return { weekOpen: true, closedReason: "", allowEntries: false, entryReason: "خارج از سشن‌های توکیو/لندن/نیویورک", active };
  }
  if (!active.includes("London_NY_Overlap")) {
    return { weekOpen: true, closedReason: "", allowEntries: false, entryReason: "ورود جدید فقط در همپوشانی لندن/نیویورک", active };
  }
  return { weekOpen: true, closedReason: "", allowEntries: true, entryReason: "در سشن: " + active.join(", "), active };
}

export function SessionClock() {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  if (!now) return null;

  const tehranP = getPartsInTZ(now, "Asia/Tehran");
  const nyP = getPartsInTZ(now, "America/New_York");
  // Live NY -> Tehran offset for *today* — correctly follows US DST changes
  // (Iran no longer observes DST) since it's recomputed every render.
  const offset = minuteOfDay(tehranP) - minuteOfDay(nyP);
  const status = marketStatus(nyP);

  return (
    <TiltCard>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-medium">سشن‌های معاملاتی</h2>
        <span
          className={`rounded-full px-2 py-0.5 text-xs ${
            status.allowEntries ? "bg-emerald-400/20 text-emerald-300" : "bg-slate-400/20 text-slate-300"
          }`}
        >
          {status.weekOpen ? (status.allowEntries ? "ورود جدید مجاز" : "ورود جدید بسته") : "بازار بسته"}
        </span>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 text-sm">
        <div className="rounded-xl border border-white/10 bg-black/20 p-3">
          <div className="text-xs text-slate-400">تهران</div>
          <div className="mt-1 font-mono font-semibold">
            {String(tehranP.hour).padStart(2, "0")}:{String(tehranP.minute).padStart(2, "0")}:
            {String(tehranP.second).padStart(2, "0")}
          </div>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 p-3">
          <div className="text-xs text-slate-400">نیویورک (مبنای سشن‌ها)</div>
          <div className="mt-1 font-mono font-semibold">
            {String(nyP.hour).padStart(2, "0")}:{String(nyP.minute).padStart(2, "0")}:
            {String(nyP.second).padStart(2, "0")}
          </div>
        </div>
      </div>

      <div className="space-y-2">
        {SESSIONS.map((w) => {
          const isActive = status.weekOpen && status.active.includes(w.key);
          const startTehran = fmtHM(w.startMin + offset);
          const endTehran = fmtHM(w.endMin + offset);
          return (
            <div
              key={w.key}
              className={`flex items-center justify-between rounded-xl border px-3 py-2 text-sm ${
                isActive ? "border-emerald-400/30 bg-emerald-400/10" : "border-white/10 bg-black/20"
              }`}
            >
              <div className="flex items-center gap-2">
                <span className={`h-2 w-2 rounded-full ${isActive ? "bg-emerald-400" : "bg-slate-500"}`} />
                <span className={isActive ? "text-emerald-200" : "text-slate-300"}>{w.nameFa}</span>
              </div>
              <span className="text-xs text-slate-400">
                {startTehran} - {endTehran} به وقت تهران
              </span>
            </div>
          );
        })}
      </div>

      <p className="mt-3 text-xs text-slate-500">{status.weekOpen ? status.entryReason : status.closedReason}</p>
    </TiltCard>
  );
}
