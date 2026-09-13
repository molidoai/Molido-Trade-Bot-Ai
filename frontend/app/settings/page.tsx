"use client";

/**
 * Settings.
 *
 * The MT5 login block is gone. Broker credentials belong on the accounts page,
 * which owns them properly -- per account, with enable/disable, and with the
 * password write-only. Having them here too meant one terminal's credentials
 * could be edited from two places that did not agree, and it put a password
 * field on a page people open to adjust a risk number.
 *
 * The API still accepts those fields; this page simply no longer sends them,
 * so nothing stored is disturbed.
 *
 * Colours come from the design tokens rather than hardcoded slate/amber/cyan
 * utilities, which were fixed to one theme and drifted from every other page.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { API, getToken } from "@/lib/auth";

type FormState = {
  symbols: string;
  timeframe: string;
  telegram_bot_token: string;
  telegram_admin_chat_id: string;
  telegram_allowed_chat_ids: string;
  default_risk_per_trade: number;
  max_daily_loss: number;
  max_drawdown: number;
  max_open_positions: number;
  telegram_bot_token_set: boolean;
};

const empty: FormState = {
  symbols: "auto",
  timeframe: "AUTO",
  telegram_bot_token: "",
  telegram_admin_chat_id: "",
  telegram_allowed_chat_ids: "",
  default_risk_per_trade: 0.0025,
  max_daily_loss: 0.02,
  max_drawdown: 0.04,
  max_open_positions: 3,
  telegram_bot_token_set: false,
};

function Field({ label, hint, children }: {
  label: string; hint?: string; children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint ? <span className="hint">{hint}</span> : null}
    </label>
  );
}

function Section({ title, note, children }: {
  title: string; note?: string; children: React.ReactNode;
}) {
  return (
    <section className="panel p-5">
      <h2 className="text-[15px] font-bold">{title}</h2>
      {note ? <p className="mt-1 text-xs text-[var(--muted)]">{note}</p> : null}
      <div className="mt-4">{children}</div>
    </section>
  );
}

export default function SettingsPage() {
  const [form, setForm] = useState<FormState>(empty);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState(false);
  const [busy, setBusy] = useState(false);

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    void (async () => {
      const token = getToken();
      if (!token) { setErr(true); setMsg("برای دیدن تنظیمات وارد شوید"); return; }
      try {
        const r = await fetch(`${API}/settings`, {
          headers: { Authorization: `Bearer ${token}` }, cache: "no-store",
        });
        if (!r.ok) {
          setErr(true);
          setMsg(r.status === 401 ? "نشست منقضی شده" : "خطا در خواندن تنظیمات");
          return;
        }
        const data = await r.json();
        setForm({
          symbols: data.symbols ?? "auto",
          timeframe: data.timeframe ?? "AUTO",
          telegram_bot_token: "",
          telegram_admin_chat_id: data.telegram_admin_chat_id ?? "",
          telegram_allowed_chat_ids: data.telegram_allowed_chat_ids ?? "",
          default_risk_per_trade: data.default_risk_per_trade ?? 0.0025,
          max_daily_loss: data.max_daily_loss ?? 0.02,
          max_drawdown: data.max_drawdown ?? 0.04,
          max_open_positions: data.max_open_positions ?? 3,
          telegram_bot_token_set: Boolean(data.telegram_bot_token_set),
        });
        setErr(false); setMsg("");
      } catch { setErr(true); setMsg("API در دسترس نیست"); }
    })();
  }, []);

  async function save() {
    const token = getToken();
    if (!token) { setErr(true); setMsg("اول وارد شوید"); return; }
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        symbols: form.symbols,
        timeframe: form.timeframe,
        telegram_admin_chat_id: form.telegram_admin_chat_id,
        telegram_allowed_chat_ids: form.telegram_allowed_chat_ids,
        default_risk_per_trade: form.default_risk_per_trade,
        max_daily_loss: form.max_daily_loss,
        max_drawdown: form.max_drawdown,
        max_open_positions: form.max_open_positions,
      };
      // Blank means "keep the stored token" -- an empty string would erase it.
      if (form.telegram_bot_token) body.telegram_bot_token = form.telegram_bot_token;

      const r = await fetch(`${API}/settings`, {
        // PUT, not PATCH -- the router only defines GET and PUT, and a
        // PATCH here returns 405 while looking like a save that failed.
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      });
      const out = await r.json().catch(() => ({}));
      if (!r.ok) {
        setErr(true);
        setMsg(out?.detail ? String(out.detail) : `خطا (${r.status})`);
        return;
      }
      setErr(false);
      setMsg("ذخیره شد");
      setForm((f) => ({
        ...f,
        telegram_bot_token: "",
        telegram_bot_token_set: f.telegram_bot_token_set || Boolean(form.telegram_bot_token),
      }));
    } catch { setErr(true); setMsg("API در دسترس نیست"); }
    finally { setBusy(false); }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <header>
        <h1>تنظیمات</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          روی سرور ذخیره می‌شود، نه در گیت.
        </p>
      </header>

      {msg ? (
        <div className="rounded-[var(--r)] border px-4 py-3 text-sm"
          style={err
            ? { borderColor: "var(--down)", background: "var(--down-soft)", color: "var(--down)" }
            : { borderColor: "var(--up)", background: "var(--up-soft)", color: "var(--up)" }}>
          {msg}
        </div>
      ) : null}

      <div className="inset flex flex-wrap items-center justify-between gap-3 p-4 text-xs">
        <span className="text-[var(--ink-2)]">
          حساب‌های بروکر و رمزشان از این صفحه جدا شده‌اند.
        </span>
        <Link href="/accounts" className="btn h-8 min-h-0 px-3 text-xs">
          رفتن به حساب‌ها
        </Link>
      </div>

      <Section title="بازار" note="نمادها و بازه‌ی زمانی که موتور روی آن ارزیابی می‌کند.">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="نمادها" hint="خالی یا auto یعنی انتخاب با موتور">
            <input className="input" dir="ltr" value={form.symbols}
              onChange={(e) => set("symbols", e.target.value)} />
          </Field>
          <Field label="تایم‌فریم" hint="AUTO ورودها را روی M15 و M5 می‌گردد">
            <select className="input" dir="ltr" value={form.timeframe}
              onChange={(e) => set("timeframe", e.target.value)}>
              <option value="AUTO">AUTO</option>
              <option value="M5">M5</option>
              <option value="M15">M15</option>
              <option value="H1">H1</option>
              <option value="H4">H4</option>
              <option value="D1">D1</option>
            </select>
          </Field>
        </div>
      </Section>

      <Section title="ریسک" note="اعداد کسری‌اند: ۰.۰۱ یعنی یک درصد.">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="ریسک هر معامله" hint="۰.۰۰۲۵ = ۰.۲۵٪">
            <input className="input num" type="number" step="0.0005" min="0.0001" max="0.05"
              value={form.default_risk_per_trade}
              onChange={(e) => set("default_risk_per_trade", Number(e.target.value))} />
          </Field>
          <Field label="سقف ضرر روزانه" hint="۰.۰۲ = ۲٪">
            <input className="input num" type="number" step="0.005" min="0.001" max="0.2"
              value={form.max_daily_loss}
              onChange={(e) => set("max_daily_loss", Number(e.target.value))} />
          </Field>
          <Field label="حداکثر افت" hint="۰.۰۴ = ۴٪">
            <input className="input num" type="number" step="0.005" min="0.001" max="0.5"
              value={form.max_drawdown}
              onChange={(e) => set("max_drawdown", Number(e.target.value))} />
          </Field>
          <Field label="حداکثر پوزیشن باز">
            <input className="input num" type="number" step="1" min="1" max="50"
              value={form.max_open_positions}
              onChange={(e) => set("max_open_positions", Number(e.target.value))} />
          </Field>
        </div>
      </Section>

      <Section title="تلگرام" note="گزارش روزانه و هشدارها از این ربات فرستاده می‌شود.">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="توکن ربات"
            hint={form.telegram_bot_token_set ? "ذخیره شده — خالی بگذارید تا تغییر نکند" : "هنوز ذخیره نشده"}>
            <input className="input" type="password" dir="ltr" autoComplete="new-password"
              placeholder={form.telegram_bot_token_set ? "بدون تغییر" : ""}
              value={form.telegram_bot_token}
              onChange={(e) => set("telegram_bot_token", e.target.value)} />
          </Field>
          <Field label="آیدی چت ادمین">
            <input className="input num" dir="ltr" value={form.telegram_admin_chat_id}
              onChange={(e) => set("telegram_admin_chat_id", e.target.value)} />
          </Field>
          <Field label="آیدی‌های مجاز" hint="با کاما جدا کنید">
            <input className="input" dir="ltr" value={form.telegram_allowed_chat_ids}
              onChange={(e) => set("telegram_allowed_chat_ids", e.target.value)} />
          </Field>
        </div>
      </Section>

      {/* Kept visible rather than dropped: it explains an absence, and an
          unexplained absence reads as a missing feature. */}
      <div className="rounded-[var(--r)] border p-4 text-xs"
        style={{ borderColor: "color-mix(in srgb, var(--warn) 35%, transparent)",
                 background: "var(--warn-soft)", color: "var(--warn)" }}>
        حالت حساب (DEMO/REAL) و روشن/خاموش کردن ربات عمداً اینجا نیست. رفتن به حساب واقعی
        از صفحه‌ی «زنده» و با تأیید دومرحله‌ای انجام می‌شود، نه با یک ذخیره‌ی ساده.
      </div>

      <div className="flex items-center gap-3 pb-4">
        <button type="button" className="btn btn-primary" disabled={busy} onClick={save}>
          {busy ? "در حال ذخیره…" : "ذخیره روی سرور"}
        </button>
      </div>
    </div>
  );
}
