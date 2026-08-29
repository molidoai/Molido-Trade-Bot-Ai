"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

type FormState = {
  trading_account_mode: string;
  master_bot_enabled: boolean;
  mt5_real_login: string;
  mt5_real_password: string;
  mt5_real_server: string;
  telegram_bot_token: string;
  telegram_admin_chat_id: string;
  default_risk_per_trade: number;
  max_daily_loss: number;
  max_drawdown: number;
  max_open_positions: number;
};

const empty: FormState = {
  trading_account_mode: "REAL",
  master_bot_enabled: true,
  mt5_real_login: "",
  mt5_real_password: "",
  mt5_real_server: "",
  telegram_bot_token: "",
  telegram_admin_chat_id: "",
  default_risk_per_trade: 0.005,
  max_daily_loss: 0.02,
  max_drawdown: 0.05,
  max_open_positions: 5,
};

export default function SettingsPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [form, setForm] = useState<FormState>(empty);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const t = localStorage.getItem("molido_token") || "";
    setToken(t);
    if (t) void load(t);
  }, []);

  async function load(tkn: string) {
    const r = await fetch(`${API}/settings`, {
      headers: { Authorization: `Bearer ${tkn}` },
      cache: "no-store",
    });
    if (!r.ok) {
      setMsg("لاگین لازم است");
      return;
    }
    const data = await r.json();
    setForm({
      ...empty,
      ...data,
      mt5_real_password: "",
      telegram_bot_token: "",
    });
    setMsg("تنظیمات از سرور خوانده شد");
  }

  async function loginOrRegister() {
    setBusy(true);
    setMsg("");
    try {
      let r = await fetch(`${API}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (r.status === 401) {
        r = await fetch(`${API}/auth/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, full_name: "Operator" }),
        });
        if (r.ok) {
          r = await fetch(`${API}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
          });
        }
      }
      if (!r.ok) {
        setMsg("ورود ناموفق");
        return;
      }
      const data = await r.json();
      const tkn = data.access_token as string;
      localStorage.setItem("molido_token", tkn);
      setToken(tkn);
      await load(tkn);
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!token) {
      setMsg("اول وارد شو");
      return;
    }
    setBusy(true);
    try {
      const body: Record<string, unknown> = { ...form };
      if (!form.mt5_real_password) delete body.mt5_real_password;
      if (!form.telegram_bot_token) delete body.telegram_bot_token;
      const r = await fetch(`${API}/settings`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });
      if (r.status === 403) {
        setMsg("فقط ادمین می‌تواند ذخیره کند");
        return;
      }
      if (!r.ok) {
        setMsg("ذخیره نشد");
        return;
      }
      setMsg("ذخیره شد روی سرور");
      setForm((f) => ({ ...f, mt5_real_password: "", telegram_bot_token: "" }));
    } finally {
      setBusy(false);
    }
  }

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  return (
    <div className="space-y-6">
      <h2 className="aurora text-3xl font-black">تنظیمات</h2>

      <div className="glass space-y-3 rounded-2xl p-5">
        <p className="text-sm text-slate-400">ورود ادمین (اولین ثبت‌نام ادمین می‌شود)</p>
        <div className="grid gap-3 md:grid-cols-3">
          <input
            className="rounded-xl border border-white/10 bg-black/30 px-3 py-2"
            placeholder="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            className="rounded-xl border border-white/10 bg-black/30 px-3 py-2"
            placeholder="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button
            type="button"
            disabled={busy}
            onClick={loginOrRegister}
            className="rounded-xl bg-cyan-500/20 px-3 py-2 text-cyan-200"
          >
            ورود / ساخت ادمین
          </button>
        </div>
      </div>

      <div className="glass space-y-4 rounded-2xl p-5">
        <div className="flex items-center justify-between">
          <p className="font-medium">LIVE</p>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.master_bot_enabled}
              onChange={(e) => set("master_bot_enabled", e.target.checked)}
            />
            مستر روشن
          </label>
        </div>
        <select
          className="w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2"
          value={form.trading_account_mode}
          onChange={(e) => set("trading_account_mode", e.target.value)}
        >
          <option value="REAL">REAL</option>
          <option value="DEMO">DEMO</option>
          <option value="PROP">PROP</option>
        </select>

        <p className="pt-2 text-sm text-slate-400">MT5 REAL</p>
        <div className="grid gap-3 md:grid-cols-3">
          <input className="rounded-xl border border-white/10 bg-black/30 px-3 py-2" placeholder="login" value={form.mt5_real_login} onChange={(e) => set("mt5_real_login", e.target.value)} />
          <input className="rounded-xl border border-white/10 bg-black/30 px-3 py-2" placeholder="password (خالی = بدون تغییر)" type="password" value={form.mt5_real_password} onChange={(e) => set("mt5_real_password", e.target.value)} />
          <input className="rounded-xl border border-white/10 bg-black/30 px-3 py-2" placeholder="server" value={form.mt5_real_server} onChange={(e) => set("mt5_real_server", e.target.value)} />
        </div>

        <p className="pt-2 text-sm text-slate-400">تلگرام</p>
        <div className="grid gap-3 md:grid-cols-2">
          <input className="rounded-xl border border-white/10 bg-black/30 px-3 py-2" placeholder="bot token (خالی = بدون تغییر)" type="password" value={form.telegram_bot_token} onChange={(e) => set("telegram_bot_token", e.target.value)} />
          <input className="rounded-xl border border-white/10 bg-black/30 px-3 py-2" placeholder="admin chat id" value={form.telegram_admin_chat_id} onChange={(e) => set("telegram_admin_chat_id", e.target.value)} />
        </div>

        <p className="pt-2 text-sm text-slate-400">ریسک</p>
        <div className="grid gap-3 md:grid-cols-4">
          <input className="rounded-xl border border-white/10 bg-black/30 px-3 py-2" type="number" step="0.001" value={form.default_risk_per_trade} onChange={(e) => set("default_risk_per_trade", Number(e.target.value))} />
          <input className="rounded-xl border border-white/10 bg-black/30 px-3 py-2" type="number" step="0.001" value={form.max_daily_loss} onChange={(e) => set("max_daily_loss", Number(e.target.value))} />
          <input className="rounded-xl border border-white/10 bg-black/30 px-3 py-2" type="number" step="0.001" value={form.max_drawdown} onChange={(e) => set("max_drawdown", Number(e.target.value))} />
          <input className="rounded-xl border border-white/10 bg-black/30 px-3 py-2" type="number" value={form.max_open_positions} onChange={(e) => set("max_open_positions", Number(e.target.value))} />
        </div>

        <button type="button" disabled={busy} onClick={save} className="rounded-xl bg-amber-400/20 px-4 py-2 text-amber-200">
          ذخیره روی سرور
        </button>
        {msg && <p className="text-sm text-cyan-300">{msg}</p>}
      </div>
    </div>
  );
}
