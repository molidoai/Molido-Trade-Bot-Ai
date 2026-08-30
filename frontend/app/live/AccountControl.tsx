"use client";

import { useEffect, useState } from "react";
import { API, getToken } from "@/lib/auth";
import { TiltCard } from "@/components/ui/TiltCard";

type OpsState = {
  master_on: boolean;
  account_mode: string;
  live: boolean;
  engine_alive: boolean;
};

const CONFIRM_TOKEN: Record<string, string> = {
  REAL: "CONFIRM_REAL",
  PROP: "CONFIRM_PROP",
};

export function AccountControl() {
  const [state, setState] = useState<OpsState | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [targetMode, setTargetMode] = useState("DEMO");
  const [confirmText, setConfirmText] = useState("");

  async function refresh() {
    const token = getToken();
    if (!token) return;
    try {
      const r = await fetch(`${API}/ops/state`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (r.ok) setState(await r.json());
    } catch {
      // transient — next poll retries
    }
  }

  useEffect(() => {
    void refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, []);

  async function call(path: string, body: unknown) {
    const token = getToken();
    if (!token) {
      setMsg("اول وارد شو");
      return null;
    }
    setBusy(true);
    setMsg("");
    try {
      const r = await fetch(`${API}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        setMsg(typeof data.detail === "string" ? data.detail : "عملیات ناموفق");
        return null;
      }
      await refresh();
      return data;
    } finally {
      setBusy(false);
    }
  }

  async function toggleMaster(on: boolean) {
    const out = await call("/ops/master", { on });
    if (out) setMsg(out.message || "انجام شد");
  }

  async function applyMode() {
    const body: Record<string, unknown> = { mode: targetMode };
    const token = CONFIRM_TOKEN[targetMode];
    if (token) body.confirm_token = confirmText;
    const out = await call("/ops/mode", body);
    if (out) {
      setMsg(out.message || "انجام شد");
      setConfirmText("");
    }
  }

  const requiredToken = CONFIRM_TOKEN[targetMode];
  const canApply = !requiredToken || confirmText === requiredToken;

  return (
    <TiltCard>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-medium">حالت حساب و مستر</h2>
        {state ? (
          <span
            className={`rounded-full px-2 py-0.5 text-xs ${
              state.live ? "bg-rose-400/20 text-rose-300" : "bg-emerald-400/20 text-emerald-300"
            }`}
          >
            {state.live ? "LIVE" : "ایمن"}
          </span>
        ) : null}
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 text-sm">
        <div className="rounded-xl border border-white/10 bg-black/20 p-3">
          <div className="text-xs text-slate-400">حالت فعلی</div>
          <div className="mt-1 font-semibold">{state?.account_mode ?? "—"}</div>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 p-3">
          <div className="text-xs text-slate-400">مستر</div>
          <div className={`mt-1 font-semibold ${state?.master_on ? "text-emerald-300" : "text-slate-400"}`}>
            {state?.master_on ? "روشن" : "خاموش"}
          </div>
        </div>
      </div>

      <div className="mb-4 flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => toggleMaster(true)}
          className="rounded-xl bg-emerald-400/20 px-3 py-2 text-sm text-emerald-200 disabled:opacity-50"
        >
          مستر روشن
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => toggleMaster(false)}
          className="rounded-xl bg-slate-400/20 px-3 py-2 text-sm text-slate-200 disabled:opacity-50"
        >
          مستر خاموش
        </button>
      </div>

      <div className="space-y-2 rounded-xl border border-white/10 bg-black/20 p-3">
        <div className="text-xs text-slate-400">تغییر حالت حساب</div>
        <select
          className="w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-sm"
          value={targetMode}
          onChange={(e) => {
            setTargetMode(e.target.value);
            setConfirmText("");
          }}
        >
          <option value="DEMO">DEMO</option>
          <option value="PROP">PROP</option>
          <option value="REAL">REAL (حساب واقعی)</option>
        </select>
        {requiredToken ? (
          <input
            className="w-full rounded-xl border border-rose-400/30 bg-black/30 px-3 py-2 text-sm"
            placeholder={`برای تأیید دقیقاً بنویس: ${requiredToken}`}
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
          />
        ) : null}
        <button
          type="button"
          disabled={busy || !canApply}
          onClick={applyMode}
          className="w-full rounded-xl bg-rose-400/20 px-3 py-2 text-sm text-rose-200 disabled:opacity-40"
        >
          اعمال حالت {targetMode}
        </button>
      </div>

      {msg ? <p className="mt-3 text-xs text-slate-400">{msg}</p> : null}
    </TiltCard>
  );
}
