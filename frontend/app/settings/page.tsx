"use client";

import { useEffect, useState } from "react";
import { API, getToken } from "@/lib/auth";

type FormState = {
  trading_account_mode: string;
  master_bot_enabled: boolean;
  mt5_login: string;
  mt5_password: string;
  mt5_server: string;
  mt5_path: string;
  symbols: string;
  timeframe: string;
  telegram_bot_token: string;
  telegram_admin_chat_id: string;
  telegram_allowed_chat_ids: string;
  default_risk_per_trade: number;
  max_daily_loss: number;
  max_drawdown: number;
  max_open_positions: number;
  mt5_password_set: boolean;
  telegram_bot_token_set: boolean;
};

const empty: FormState = {
  trading_account_mode: "DEMO",
  master_bot_enabled: true,
  mt5_login: "",
  mt5_password: "",
  mt5_server: "",
  mt5_path: "",
  symbols: "auto",
  timeframe: "AUTO",
  telegram_bot_token: "",
  telegram_admin_chat_id: "",
  telegram_allowed_chat_ids: "",
  default_risk_per_trade: 0.0025,
  max_daily_loss: 0.02,
  max_drawdown: 0.04,
  max_open_positions: 3,
  mt5_password_set: false,
  telegram_bot_token_set: false,
};

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-sm text-slate-300">{label}</span>
      {children}
      {hint ? <span className="block text-xs text-slate-500">{hint}</span> : null}
    </label>
  );
}

const inputCls = "w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2";

export default function SettingsPage() {
  const [form, setForm] = useState<FormState>(empty);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const t = getToken();
    if (t) void load(t);
  }, []);

  async function load(tkn: string) {
    const r = await fetch(`${API}/settings`, {
      headers: { Authorization: `Bearer ${tkn}` },
      cache: "no-store",
    });
    if (!r.ok) {
      setMsg("نشست منقضی است. دوباره وارد شو.");
      return;
    }
    const data = await r.json();
    setForm({
      ...empty,
      ...data,
      mt5_login: data.mt5_login || data.mt5_real_login || "",
      mt5_server: data.mt5_server || data.mt5_real_server || "",
      mt5_path: data.mt5_path || data.mt5_real_path || "",
      mt5_password: "",
      telegram_bot_token: "",
      mt5_password_set: Boolean(data.mt5_password_set || data.mt5_real_password_set),
      telegram_bot_token_set: Boolean(data.telegram_bot_token_set),
    });
    setMsg("تنظیمات از سرور خوانده شد");
  }

  async function save() {
    const token = getToken();
    if (!token) {
      setMsg("اول وارد شو");
      return;
    }
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        trading_account_mode: form.trading_account_mode,
        master_bot_enabled: form.master_bot_enabled,
        mt5_login: form.mt5_login,
        mt5_server: form.mt5_server,
        mt5_path: form.mt5_path,
        symbols: form.symbols,
        timeframe: form.timeframe,
        telegram_admin_chat_id: form.telegram_admin_chat_id,
        telegram_allowed_chat_ids: form.telegram_allowed_chat_ids,
        default_risk_per_trade: form.default_risk_per_trade,
        max_daily_loss: form.max_daily_loss,
        max_drawdown: form.max_drawdown,
        max_open_positions: form.max_open_positions,
      };
      if (form.mt5_password) body.mt5_password = form.mt5_password;
      if (form.telegram_bot_token) body.telegram_bot_token = form.telegram_bot_token;
      const r = await fetch(`${API}/settings`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });
      if (r.status === 403) {
        setMsg("فقط مالک می‌تواند ذخیره کند");
        return;
      }
      if (!r.ok) {
        setMsg("ذخیره نشد");
        return;
      }
      setMsg("ذخیره شد روی سرور. موتور از همین فایل می‌خواند.");
      setForm((f) => ({
        ...f,
        mt5_password: "",
        telegram_bot_token: "",
        mt5_password_set: f.mt5_password_set || Boolean(form.mt5_password),
        telegram_bot_token_set: f.telegram_bot_token_set || Boolean(form.telegram_bot_token),
      }));
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
      <p className="text-sm text-slate-400">
        همه مقدارهای لازم را همین‌جا وارد کن. روی سرور ذخیره می‌شود، نه داخل گیت. ورود جداگانه از صفحه لاگین است.
      </p>

      <div className="glass space-y-5 rounded-2xl p-5">
        <div className="flex items-center justify-between gap-4">
          <p className="font-medium">حساب و مستر</p>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.master_bot_enabled} onChange={(e) => set("master_bot_enabled", e.target.checked)} />
            مستر روشن
          </label>
        </div>
        <Field label="حالت حساب">
          <select className={inputCls} value={form.trading_account_mode} onChange={(e) => set("trading_account_mode", e.target.value)}>
            <option value="DEMO">DEMO</option>
            <option value="REAL">REAL (حساب واقعی)</option>
            <option value="PROP">PROP</option>
          </select>
        </Field>

        <p className="pt-1 text-sm font-medium text-slate-300">متاتریدر ۵</p>
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="لاگین MT5">
            <input className={inputCls} value={form.mt5_login} onChange={(e) => set("mt5_login", e.target.value)} />
          </Field>
          <Field label="رمز MT5" hint={form.mt5_password_set ? "ذخیره شده. خالی بگذار اگر عوض نمی‌کنی." : "هنوز ذخیره نشده"}>
            <input className={inputCls} type="password" value={form.mt5_password} onChange={(e) => set("mt5_password", e.target.value)} />
          </Field>
          <Field label="سرور بروکر" hint="مثل RoboForex-Demo یا نام سرور حساب واقعی">
            <input className={inputCls} value={form.mt5_server} onChange={(e) => set("mt5_server", e.target.value)} />
          </Field>
          <Field label="مسیر ترمینال" hint="اختیاری. روی ویندوز یا Wine، مسیر terminal64.exe">
            <input className={inputCls} value={form.mt5_path} onChange={(e) => set("mt5_path", e.target.value)} />
          </Field>
        </div>

        <p className="pt-1 text-sm font-medium text-slate-300">بازار</p>
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="نمادها" hint="خالی یا auto یعنی مغز از یونیورس انتخاب می‌کند ( majores + چند کراس، بدون M1 )">
            <input className={inputCls} value={form.symbols} onChange={(e) => set("symbols", e.target.value)} />
          </Field>
          <Field label="تایم‌فریم" hint="AUTO = M15 + فیلتر H1؛ M5 فقط در overlap اگر spread خوب باشد.">
            <select className={inputCls} value={form.timeframe} onChange={(e) => set("timeframe", e.target.value)}>
              <option value="AUTO">AUTO (مغز)</option>
              <option value="M5">M5</option>
              <option value="M15">M15</option>
              <option value="H1">H1</option>
              <option value="H4">H4</option>
              <option value="D1">D1</option>
            </select>
          </Field>
        </div>

        <p className="pt-1 text-sm font-medium text-slate-300">تلگرام</p>
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="توکن ربات" hint={form.telegram_bot_token_set ? "ذخیره شده. خالی بگذار اگر عوض نمی‌کنی." : "هنوز ذخیره نشده"}>
            <input className={inputCls} type="password" value={form.telegram_bot_token} onChange={(e) => set("telegram_bot_token", e.target.value)} />
          </Field>
          <Field label="آیدی چت ادمین">
            <input className={inputCls} value={form.telegram_admin_chat_id} onChange={(e) => set("telegram_admin_chat_id", e.target.value)} />
          </Field>
          <Field label="آیدی‌های مجاز" hint="چند تا را با کاما جدا کن">
            <input className={inputCls} value={form.telegram_allowed_chat_ids} onChange={(e) => set("telegram_allowed_chat_ids", e.target.value)} />
          </Field>
        </div>

        <p className="pt-1 text-sm font-medium text-slate-300">ریسک</p>
        <div className="grid gap-3 md:grid-cols-4">
          <Field label="ریسک هر معامله" hint="مثلا ۰.۰۰۲۵ یعنی ۰.۲۵٪">
            <input className={inputCls} type="number" step="0.001" value={form.default_risk_per_trade} onChange={(e) => set("default_risk_per_trade", Number(e.target.value))} />
          </Field>
          <Field label="سقف ضرر روزانه" hint="مثلا ۰.۰۲ یعنی ۲٪">
            <input className={inputCls} type="number" step="0.001" value={form.max_daily_loss} onChange={(e) => set("max_daily_loss", Number(e.target.value))} />
          </Field>
          <Field label="حداکثر دراودان" hint="مثلا ۰.۰۴ یعنی ۴٪">
            <input className={inputCls} type="number" step="0.001" value={form.max_drawdown} onChange={(e) => set("max_drawdown", Number(e.target.value))} />
          </Field>
          <Field label="حداکثر پوزیشن باز">
            <input className={inputCls} type="number" value={form.max_open_positions} onChange={(e) => set("max_open_positions", Number(e.target.value))} />
          </Field>
        </div>

        <button type="button" disabled={busy} onClick={save} className="rounded-xl bg-amber-400/20 px-4 py-2 text-amber-200">
          ذخیره روی سرور
        </button>
        {msg && <p className="text-sm text-cyan-300">{msg}</p>}
      </div>
    </div>
  );
}
