"use client";

/**
 * Trading account management.
 *
 * The engine supervises one runner per enabled entry in the accounts list.
 * Until this page existed the only way to add one was running a shell script
 * on the server, and there was no way to see or disable an account at all.
 *
 * Deliberately mirrors the API's safety rules rather than working around them:
 * a new account is created disabled and in DEMO, passwords are write-only, and
 * going live still happens on the live page behind its confirm-token gate.
 */

import { useCallback, useEffect, useState } from "react";
import { API, getToken } from "@/lib/auth";
import { TiltCard } from "@/components/ui/TiltCard";

type Account = {
  id: string;
  name?: string;
  enabled?: boolean;
  trading_account_mode?: string;
  mt5_login?: string;
  mt5_server?: string;
  mt5_password_set?: boolean;
  rpc_port?: number;
  symbols?: string;
  timeframe?: string;
  prop_initial_balance?: number;
  prop_max_loss_pct?: number;
  implicit?: boolean;
};

const EMPTY = {
  id: "",
  name: "",
  mt5_login: "",
  mt5_password: "",
  mt5_server: "",
  rpc_port: 8002,
  symbols: "",
  timeframe: "auto",
  prop_initial_balance: 0,
  prop_max_loss_pct: 0.1,
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
    <label className="block">
      <span className="mb-1 block text-xs text-slate-400">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-[11px] text-slate-500">{hint}</span> : null}
    </label>
  );
}

const INPUT =
  "w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-sm outline-none focus:border-cyan-400/50";

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [implicit, setImplicit] = useState(false);
  const [form, setForm] = useState({ ...EMPTY });
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setMsg("برای مدیریت حساب‌ها وارد شو");
      return;
    }
    try {
      const r = await fetch(`${API}/accounts`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (!r.ok) {
        setMsg(r.status === 401 ? "نشست منقضی است. دوباره وارد شو." : "خطا در خواندن حساب‌ها");
        return;
      }
      const data = await r.json();
      setAccounts(data.accounts || []);
      setImplicit(!!data.implicit);
      setMsg("");
    } catch {
      setMsg("API در دسترس نیست");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function call(path: string, init: RequestInit, ok: string) {
    const token = getToken();
    if (!token) return setMsg("اول وارد شو");
    setBusy(true);
    try {
      const r = await fetch(`${API}${path}`, {
        ...init,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
          ...(init.headers || {}),
        },
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setMsg(body?.detail ? String(body.detail) : `خطا (${r.status})`);
      } else {
        setMsg(ok);
        await load();
      }
    } catch {
      setMsg("API در دسترس نیست");
    } finally {
      setBusy(false);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const payload: Record<string, unknown> = {
      id: form.id.trim().toLowerCase(),
      name: form.name.trim() || form.id.trim(),
      mt5_login: form.mt5_login.trim(),
      mt5_server: form.mt5_server.trim(),
      rpc_port: Number(form.rpc_port) || 8002,
      prop_initial_balance: Number(form.prop_initial_balance) || 0,
      prop_max_loss_pct: Number(form.prop_max_loss_pct) || 0.1,
    };
    // Empty password means "keep whatever is stored" -- the API treats it that
    // way, so never send an empty string as if it were a new value.
    if (form.mt5_password) payload.mt5_password = form.mt5_password;
    if (form.symbols.trim()) payload.symbols = form.symbols.trim();
    if (form.timeframe.trim()) payload.timeframe = form.timeframe.trim();

    await call("/accounts", { method: "POST", body: JSON.stringify(payload) }, "ذخیره شد");
    setForm({ ...EMPTY });
  }

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.25em] text-cyan-300/80">accounts</p>
        <h2 className="aurora mt-1 text-3xl font-black">حساب‌های معاملاتی</h2>
      </div>

      {implicit ? (
        <div className="rounded-2xl border border-amber-400/25 bg-amber-400/5 p-4 text-sm text-amber-200">
          هنوز فهرست حساب تعریف نشده. موتور یک حساب «default» از تنظیمات اصلی می‌سازد و
          همان را معامله می‌کند. با افزودن اولین حساب، این حساب هم به فهرست منتقل می‌شود
          و رفتارش تغییری نمی‌کند.
        </div>
      ) : null}

      <TiltCard>
        <h3 className="mb-4 font-medium">حساب‌های فعلی</h3>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="text-xs text-slate-400">
              <tr>
                <th className="p-2 text-right">شناسه</th>
                <th className="p-2 text-right">نام</th>
                <th className="p-2 text-right">لاگین</th>
                <th className="p-2 text-right">سرور</th>
                <th className="p-2 text-right">حالت</th>
                <th className="p-2 text-right">پورت</th>
                <th className="p-2 text-right">وضعیت</th>
                <th className="p-2 text-right"></th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((a) => (
                <tr key={a.id} className="border-t border-white/5">
                  <td className="p-2 font-mono text-xs">{a.id}</td>
                  <td className="p-2">{a.name || "—"}</td>
                  <td className="p-2 font-mono text-xs">{a.mt5_login || "—"}</td>
                  <td className="p-2 text-xs">{a.mt5_server || "—"}</td>
                  <td className="p-2">
                    <span
                      className={
                        a.trading_account_mode === "REAL"
                          ? "text-rose-300"
                          : a.trading_account_mode === "PROP"
                            ? "text-amber-300"
                            : "text-emerald-300"
                      }
                    >
                      {a.trading_account_mode || "DEMO"}
                    </span>
                  </td>
                  <td className="p-2 font-mono text-xs">{a.rpc_port ?? "—"}</td>
                  <td className="p-2">
                    {a.enabled ? (
                      <span className="text-emerald-300">فعال</span>
                    ) : (
                      <span className="text-slate-500">غیرفعال</span>
                    )}
                  </td>
                  <td className="p-2 text-left">
                    <div className="flex justify-end gap-2">
                      <button
                        disabled={busy || a.implicit}
                        onClick={() =>
                          call(
                            `/accounts/${encodeURIComponent(a.id)}/enabled?on=${a.enabled ? "false" : "true"}`,
                            { method: "POST" },
                            a.enabled ? "غیرفعال شد" : "فعال شد",
                          )
                        }
                        className="rounded-lg border border-white/10 px-2 py-1 text-xs hover:border-cyan-400/40 disabled:opacity-40"
                      >
                        {a.enabled ? "توقف" : "فعال‌سازی"}
                      </button>
                      <button
                        disabled={busy || a.id === "default"}
                        onClick={() => {
                          if (!confirm(`حساب «${a.id}» حذف شود؟`)) return;
                          void call(
                            `/accounts/${encodeURIComponent(a.id)}`,
                            { method: "DELETE" },
                            "حذف شد",
                          );
                        }}
                        className="rounded-lg border border-rose-400/20 px-2 py-1 text-xs text-rose-300 hover:border-rose-400/50 disabled:opacity-30"
                      >
                        حذف
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {accounts.length === 0 ? (
                <tr>
                  <td className="p-3 text-slate-500" colSpan={8}>
                    حسابی ثبت نشده
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </TiltCard>

      <TiltCard>
        <h3 className="mb-1 font-medium">افزودن یا ویرایش حساب</h3>
        <p className="mb-4 text-xs text-slate-500">
          حساب جدید همیشه <b>غیرفعال</b> و در حالت <b>DEMO</b> ساخته می‌شود؛ افزودن حساب
          هرگز به‌خودی‌خود معامله‌ی زنده شروع نمی‌کند. تغییر حالت به REAL فقط از صفحه‌ی
          معاملات زنده و با توکن تأیید انجام می‌شود.
        </p>
        <form onSubmit={submit} className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Field label="شناسه" hint="حروف کوچک، عدد، - یا _ (مثلاً acc2)">
            <input
              required
              className={INPUT}
              value={form.id}
              onChange={(e) => setForm({ ...form, id: e.target.value })}
              placeholder="acc2"
            />
          </Field>
          <Field label="نام نمایشی">
            <input
              className={INPUT}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="FundedNext 15K"
            />
          </Field>
          <Field label="شماره حساب MT5">
            <input
              required
              className={INPUT}
              value={form.mt5_login}
              onChange={(e) => setForm({ ...form, mt5_login: e.target.value })}
              inputMode="numeric"
            />
          </Field>
          <Field label="سرور MT5">
            <input
              required
              className={INPUT}
              value={form.mt5_server}
              onChange={(e) => setForm({ ...form, mt5_server: e.target.value })}
              placeholder="FundedNext-Server 3"
            />
          </Field>
          <Field label="رمز" hint="خالی بگذارید تا رمز ذخیره‌شده تغییر نکند. هرگز نمایش داده نمی‌شود.">
            <input
              type="password"
              autoComplete="new-password"
              className={INPUT}
              value={form.mt5_password}
              onChange={(e) => setForm({ ...form, mt5_password: e.target.value })}
            />
          </Field>
          <Field label="پورت RPC" hint="هر حساب ترمینال و پورت جداگانه دارد (۸۰۰۱، ۸۰۰۲، …)">
            <input
              className={INPUT}
              value={form.rpc_port}
              onChange={(e) => setForm({ ...form, rpc_port: Number(e.target.value) })}
              inputMode="numeric"
            />
          </Field>
          <Field label="نمادها" hint="خالی = مثل حساب اصلی. ترتیب = اولویت.">
            <input
              className={INPUT}
              value={form.symbols}
              onChange={(e) => setForm({ ...form, symbols: e.target.value })}
              placeholder="XAUUSD,EURUSD,GBPUSD"
            />
          </Field>
          <Field label="تایم‌فریم" hint="auto = جاروب M15 و M5">
            <input
              className={INPUT}
              value={form.timeframe}
              onChange={(e) => setForm({ ...form, timeframe: e.target.value })}
            />
          </Field>
          <Field
            label="مانده‌ی اولیه‌ی چلنج (پراپ)"
            hint="۰ = غیرفعال. برای چلنج ۱۵ هزار دلاری: 15000"
          >
            <input
              className={INPUT}
              value={form.prop_initial_balance}
              onChange={(e) =>
                setForm({ ...form, prop_initial_balance: Number(e.target.value) })
              }
              inputMode="decimal"
            />
          </Field>
          <Field label="حداکثر ضرر شرکت" hint="۰.۱۰ یعنی ۱۰٪ — موتور زیر این کف معامله نمی‌کند">
            <input
              className={INPUT}
              value={form.prop_max_loss_pct}
              onChange={(e) => setForm({ ...form, prop_max_loss_pct: Number(e.target.value) })}
              inputMode="decimal"
            />
          </Field>
          <div className="md:col-span-2">
            {form.prop_initial_balance > 0 ? (
              <p className="mb-3 text-xs text-amber-200">
                کف محافظ: موتور زیر{" "}
                <b>
                  {(
                    Number(form.prop_initial_balance) *
                    (1 - Number(form.prop_max_loss_pct))
                  ).toLocaleString("fa-IR", { maximumFractionDigits: 2 })}
                </b>{" "}
                هیچ معامله‌ای باز نمی‌کند.
              </p>
            ) : null}
            <button
              type="submit"
              disabled={busy}
              className="rounded-xl border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm text-cyan-200 hover:border-cyan-400/60 disabled:opacity-40"
            >
              ذخیره حساب
            </button>
            {msg ? <span className="mr-3 text-xs text-slate-400">{msg}</span> : null}
          </div>
        </form>
      </TiltCard>

      <p className="text-xs text-slate-500">
        هر حساب یک ترمینال MT5 جداگانه لازم دارد. پس از افزودن، ترمینال دوم باید روی سرور
        بالا باشد و پورتش به شبکه‌ی داکر باز شده باشد، وگرنه حساب فعال می‌شود ولی وصل نمی‌شود.
      </p>
    </div>
  );
}
