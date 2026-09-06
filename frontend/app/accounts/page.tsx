"use client";

/**
 * Trading accounts.
 *
 * Rewritten because adding an account asked for ten fields when four decide
 * anything, and two of the ten were traps. `rpc_port` defaulted to 8002 for
 * every new account while the uniqueness check rejects a duplicate, so adding
 * a second account failed with a port conflict the person had no reason to
 * understand -- the port is now assigned here, from the ports already in use.
 * `id` was likewise asked for and is now derived from the name, since it only
 * has to be unique and URL-safe.
 *
 * Everything else moved behind "تنظیمات پیشرفته", closed by default. The API
 * is unchanged: POST is an upsert, so editing is the same call with the same
 * id, and a blank password means "keep the stored one".
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { API, getToken } from "@/lib/auth";

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

type Form = {
  id: string;
  name: string;
  mt5_login: string;
  mt5_server: string;
  mt5_password: string;
  symbols: string;
  timeframe: string;
  prop_initial_balance: string;
  prop_max_loss_pct: string;
};

const EMPTY: Form = {
  id: "",
  name: "",
  mt5_login: "",
  mt5_server: "",
  mt5_password: "",
  symbols: "",
  timeframe: "auto",
  prop_initial_balance: "",
  prop_max_loss_pct: "",
};

/** Lowercase, URL-safe, stable. Falls back to the login so a nameless entry
 *  still gets something meaningful rather than "account". */
function slug(name: string, login: string): string {
  const base = (name || "").trim().toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  if (base) return base.slice(0, 32);
  const digits = (login || "").replace(/[^0-9]/g, "");
  return digits ? `acc-${digits.slice(-6)}` : "";
}

const INPUT =
  "w-full rounded-xl border border-[var(--line)] bg-black/20 px-3 py-2.5 text-sm outline-none " +
  "transition focus:border-cyan-400/60 focus:ring-1 focus:ring-cyan-400/30";

function Field({ label, hint, children }: {
  label: string; hint?: string; children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-[var(--muted)]">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-[11px] text-[var(--muted)]">{hint}</span> : null}
    </label>
  );
}

function Pill({ tone, children }: { tone: "on" | "off" | "warn"; children: React.ReactNode }) {
  const cls = {
    on: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
    off: "border-white/15 bg-white/5 text-[var(--muted)]",
    warn: "border-amber-400/30 bg-amber-400/10 text-amber-300",
  }[tone];
  return (
    <span className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${cls}`}>
      {children}
    </span>
  );
}

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [implicit, setImplicit] = useState(false);
  const [form, setForm] = useState<Form>({ ...EMPTY });
  const [editing, setEditing] = useState<string | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const token = getToken();
    if (!token) { setErr(true); setMsg("برای مدیریت حساب‌ها وارد شوید"); return; }
    try {
      const r = await fetch(`${API}/accounts`, {
        headers: { Authorization: `Bearer ${token}` }, cache: "no-store",
      });
      if (!r.ok) {
        setErr(true);
        setMsg(r.status === 401 ? "نشست منقضی شده. دوباره وارد شوید." : "خطا در خواندن حساب‌ها");
        return;
      }
      const data = await r.json();
      setAccounts(data.accounts || []);
      setImplicit(!!data.implicit);
      setErr(false); setMsg("");
    } catch { setErr(true); setMsg("API در دسترس نیست"); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  // Assigned here rather than asked for: the API rejects a duplicate port, and
  // nobody adding an account knows or cares which number is free.
  const nextPort = useMemo(() => {
    const used = new Set(accounts.map((a) => Number(a.rpc_port) || 0));
    let p = 8001;
    while (used.has(p)) p += 1;
    return p;
  }, [accounts]);

  async function call(path: string, init: RequestInit, ok: string) {
    const token = getToken();
    if (!token) { setErr(true); setMsg("اول وارد شوید"); return false; }
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
        setErr(true);
        setMsg(body?.detail ? String(body.detail) : `خطا (${r.status})`);
        return false;
      }
      setErr(false); setMsg(ok);
      await load();
      return true;
    } catch { setErr(true); setMsg("API در دسترس نیست"); return false; }
    finally { setBusy(false); }
  }

  function startEdit(a: Account) {
    setEditing(a.id);
    setForm({
      id: a.id,
      name: a.name || "",
      mt5_login: a.mt5_login || "",
      mt5_server: a.mt5_server || "",
      mt5_password: "",           // never prefill; blank keeps the stored one
      symbols: a.symbols || "",
      timeframe: a.timeframe || "auto",
      prop_initial_balance: a.prop_initial_balance ? String(a.prop_initial_balance) : "",
      prop_max_loss_pct: a.prop_max_loss_pct ? String(a.prop_max_loss_pct) : "",
    });
    setAdvanced(false);
    setMsg("");
    if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function cancelEdit() {
    setEditing(null);
    setForm({ ...EMPTY });
    setAdvanced(false);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const id = editing || slug(form.name, form.mt5_login);
    if (!id) { setErr(true); setMsg("نام یا شماره حساب لازم است"); return; }
    if (!form.mt5_login.trim() || !form.mt5_server.trim()) {
      setErr(true); setMsg("شماره حساب و سرور الزامی است"); return;
    }
    if (!editing && !form.mt5_password) {
      setErr(true); setMsg("برای حساب جدید رمز لازم است"); return;
    }

    const payload: Record<string, unknown> = {
      id,
      name: form.name.trim() || id,
      mt5_login: form.mt5_login.trim(),
      mt5_server: form.mt5_server.trim(),
      rpc_port: editing
        ? (accounts.find((a) => a.id === editing)?.rpc_port ?? nextPort)
        : nextPort,
    };
    // Blank means "keep the stored password" -- never send an empty string as
    // though it were a new value.
    if (form.mt5_password) payload.mt5_password = form.mt5_password;
    if (form.symbols.trim()) payload.symbols = form.symbols.trim();
    if (form.timeframe.trim()) payload.timeframe = form.timeframe.trim();
    if (form.prop_initial_balance) payload.prop_initial_balance = Number(form.prop_initial_balance);
    if (form.prop_max_loss_pct) payload.prop_max_loss_pct = Number(form.prop_max_loss_pct);

    const ok = await call("/accounts", { method: "POST", body: JSON.stringify(payload) },
      editing ? "حساب ویرایش شد" : "حساب افزوده شد — غیرفعال و در حالت دمو");
    if (ok) cancelEdit();
  }

  async function toggle(a: Account) {
    await call(`/accounts/${a.id}/enabled?on=${!a.enabled}`, { method: "POST" },
      a.enabled ? "غیرفعال شد" : "فعال شد");
  }

  async function remove(id: string) {
    const ok = await call(`/accounts/${id}`, { method: "DELETE" }, "حساب حذف شد");
    if (ok) setConfirmDelete(null);
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <header>
        <p className="text-xs uppercase tracking-[0.25em] text-cyan-300/70">accounts</p>
        <h1 className="aurora mt-1 text-3xl font-black">حساب‌های معاملاتی</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          هر حساب فعال، یک اجراکننده‌ی مستقل در موتور دارد.
        </p>
      </header>

      {msg ? (
        <div className={`rounded-xl border px-4 py-3 text-sm ${
          err ? "border-rose-400/30 bg-rose-400/10 text-rose-200"
              : "border-emerald-400/30 bg-emerald-400/10 text-emerald-200"}`}>
          {msg}
        </div>
      ) : null}

      {implicit ? (
        <div className="rounded-xl border border-amber-400/25 bg-amber-400/5 p-4 text-sm text-amber-200">
          هنوز فهرستی تعریف نشده. موتور یک حساب «default» از تنظیمات اصلی می‌سازد و همان را
          معامله می‌کند. با افزودن اولین حساب، این حساب هم به فهرست منتقل می‌شود بدون اینکه
          رفتارش تغییر کند.
        </div>
      ) : null}

      {/* ---------------- add / edit ---------------- */}
      <section className="rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-5 sm:p-6">
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-lg font-bold">
            {editing ? `ویرایش «${editing}»` : "افزودن حساب"}
          </h2>
          {editing ? (
            <button type="button" onClick={cancelEdit}
              className="rounded-lg border border-[var(--line)] px-3 py-1.5 text-xs">
              انصراف
            </button>
          ) : null}
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="نام" hint="فقط برای شناسایی خودتان">
              <input className={INPUT} value={form.name} placeholder="مثلاً روبوفارکس دمو"
                onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
            <Field label="شماره حساب">
              <input className={INPUT} value={form.mt5_login} inputMode="numeric"
                placeholder="12345678"
                onChange={(e) => setForm({ ...form, mt5_login: e.target.value })} />
            </Field>
            <Field label="سرور" hint="دقیقاً همان‌طور که کارگزار می‌دهد">
              <input className={INPUT} value={form.mt5_server} dir="ltr"
                placeholder="RoboForex-Demo"
                onChange={(e) => setForm({ ...form, mt5_server: e.target.value })} />
            </Field>
          </div>

          <Field label="رمز" hint={editing ? "خالی بگذارید تا رمز فعلی حفظ شود" : undefined}>
            <input className={INPUT} type="password" value={form.mt5_password} dir="ltr"
              autoComplete="new-password"
              placeholder={editing ? "بدون تغییر" : ""}
              onChange={(e) => setForm({ ...form, mt5_password: e.target.value })} />
          </Field>

          <button type="button" onClick={() => setAdvanced(!advanced)}
            className="text-xs text-cyan-300/80 hover:text-cyan-200">
            {advanced ? "بستن تنظیمات پیشرفته" : "تنظیمات پیشرفته"}
          </button>

          {advanced ? (
            <div className="grid gap-4 rounded-xl border border-[var(--line)] p-4 sm:grid-cols-2">
              <Field label="نمادها" hint="خالی = پیش‌فرض موتور">
                <input className={INPUT} value={form.symbols} dir="ltr" placeholder="XAUUSD,EURUSD"
                  onChange={(e) => setForm({ ...form, symbols: e.target.value })} />
              </Field>
              <Field label="تایم‌فریم" hint="auto یا H1 / M15 / M5">
                <input className={INPUT} value={form.timeframe} dir="ltr"
                  onChange={(e) => setForm({ ...form, timeframe: e.target.value })} />
              </Field>
              <Field label="موجودی اولیه‌ی پراپ"
                hint="کف سختی که چلنج را زنده نگه می‌دارد. ۰ یعنی غیرفعال.">
                <input className={INPUT} value={form.prop_initial_balance} inputMode="decimal"
                  onChange={(e) => setForm({ ...form, prop_initial_balance: e.target.value })} />
              </Field>
              <Field label="حداکثر افت مجاز پراپ" hint="مثلاً 0.1 برای ۱۰٪">
                <input className={INPUT} value={form.prop_max_loss_pct} inputMode="decimal"
                  onChange={(e) => setForm({ ...form, prop_max_loss_pct: e.target.value })} />
              </Field>
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-3 pt-1">
            <button type="submit" disabled={busy}
              className="rounded-xl border border-cyan-400/30 bg-cyan-400/15 px-5 py-2.5 text-sm font-medium text-cyan-100 transition hover:bg-cyan-400/25 disabled:opacity-50">
              {busy ? "..." : editing ? "ذخیره‌ی تغییرات" : "افزودن حساب"}
            </button>
            {!editing ? (
              <span className="text-xs text-[var(--muted)]">
                حساب جدید غیرفعال و در حالت دمو ساخته می‌شود.
              </span>
            ) : null}
          </div>
        </form>
      </section>

      {/* ---------------- list ---------------- */}
      <section className="space-y-3">
        <h2 className="text-lg font-bold">حساب‌های موجود ({accounts.length})</h2>

        {accounts.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[var(--line)] p-10 text-center text-sm text-[var(--muted)]">
            هنوز حسابی ثبت نشده.
          </div>
        ) : null}

        {accounts.map((a) => (
          <div key={a.id}
            className="rounded-2xl border border-[var(--line)] bg-[var(--panel)] p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-bold">{a.name || a.id}</span>
                  <Pill tone={a.enabled ? "on" : "off"}>{a.enabled ? "فعال" : "غیرفعال"}</Pill>
                  <Pill tone={a.trading_account_mode === "REAL" ? "warn" : "off"}>
                    {a.trading_account_mode || "DEMO"}
                  </Pill>
                  {!a.mt5_password_set ? <Pill tone="warn">رمز ندارد</Pill> : null}
                </div>
                <div dir="ltr" className="mt-2 text-left text-xs text-[var(--muted)]">
                  {a.mt5_login || "—"} @ {a.mt5_server || "—"}
                  <span className="mx-2 opacity-40">·</span>
                  port {a.rpc_port ?? "—"}
                  {a.timeframe ? <><span className="mx-2 opacity-40">·</span>{a.timeframe}</> : null}
                </div>
              </div>

              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <button type="button" onClick={() => toggle(a)} disabled={busy}
                  className="rounded-lg border border-[var(--line)] px-3 py-1.5 text-xs transition hover:bg-white/5 disabled:opacity-50">
                  {a.enabled ? "غیرفعال کن" : "فعال کن"}
                </button>
                <button type="button" onClick={() => startEdit(a)} disabled={busy}
                  className="rounded-lg border border-[var(--line)] px-3 py-1.5 text-xs transition hover:bg-white/5 disabled:opacity-50">
                  ویرایش
                </button>
                {a.id !== "default" ? (
                  <button type="button" onClick={() => setConfirmDelete(a.id)} disabled={busy}
                    className="rounded-lg border border-rose-400/30 px-3 py-1.5 text-xs text-rose-300 transition hover:bg-rose-400/10 disabled:opacity-50">
                    حذف
                  </button>
                ) : null}
              </div>
            </div>

            {/* Deleting an account the bot may be trading is not undoable, so it
                asks in place rather than behind a browser dialog that is easy
                to dismiss without reading. */}
            {confirmDelete === a.id ? (
              <div className="mt-4 rounded-xl border border-rose-400/30 bg-rose-400/5 p-4">
                <p className="text-sm text-rose-200">
                  حساب «{a.name || a.id}» حذف شود؟ اگر فعال باشد، اجراکننده‌اش متوقف می‌شود.
                  این کار برگشت‌پذیر نیست.
                </p>
                <div className="mt-3 flex gap-2">
                  <button type="button" onClick={() => remove(a.id)} disabled={busy}
                    className="rounded-lg border border-rose-400/40 bg-rose-400/15 px-4 py-1.5 text-xs text-rose-100">
                    بله، حذف کن
                  </button>
                  <button type="button" onClick={() => setConfirmDelete(null)}
                    className="rounded-lg border border-[var(--line)] px-4 py-1.5 text-xs">
                    انصراف
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        ))}
      </section>

      <p className="pb-4 text-xs text-[var(--muted)]">
        رفتن به حساب واقعی از این صفحه ممکن نیست — آن کار در صفحه‌ی «معاملات زنده» و پشت
        تأیید دو مرحله‌ای انجام می‌شود.
      </p>
    </div>
  );
}
