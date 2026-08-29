"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { API, setSession } from "@/lib/auth";

function strength(pw: string): { n: number; label: string } {
  let n = 0;
  if (pw.length >= 8) n += 1;
  if (pw.length >= 12) n += 1;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) n += 1;
  if (/\d/.test(pw)) n += 1;
  if (/[^A-Za-z0-9]/.test(pw)) n += 1;
  const label = ["ضعیف", "ضعیف", "متوسط", "خوب", "قوی", "عالی"][n] || "ضعیف";
  return { n, label };
}

export default function LoginPage() {
  const router = useRouter();
  const [ownerExists, setOwnerExists] = useState<boolean | null>(null);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [caps, setCaps] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [now, setNow] = useState("");

  useEffect(() => {
    const tick = () => {
      setNow(
        new Date().toLocaleString("fa-IR", {
          timeZone: "Asia/Tehran",
          dateStyle: "medium",
          timeStyle: "medium",
        })
      );
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const r = await fetch(`${API}/auth/bootstrap`, { cache: "no-store" });
        const data = await r.json();
        setOwnerExists(Boolean(data.owner_exists));
      } catch {
        setOwnerExists(true);
        setMsg("API در دسترس نیست");
      }
    })();
  }, []);

  const meter = useMemo(() => strength(password), [password]);
  const setup = ownerExists === false;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setMsg("");
    if (setup) {
      if (password !== confirm) {
        setMsg("دو رمز یکی نیستند");
        return;
      }
      if (password.length < 8) {
        setMsg("رمز حداقل ۸ کاراکتر");
        return;
      }
    }
    setBusy(true);
    try {
      if (setup) {
        const r = await fetch(`${API}/auth/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, full_name: fullName || "Owner" }),
        });
        if (!r.ok) {
          const err = await r.json().catch(() => ({}));
          setMsg(err.detail || "ساخت مالک نشد");
          return;
        }
      }
      const r = await fetch(`${API}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        setMsg(typeof data.detail === "string" ? data.detail : "ورود ناموفق");
        return;
      }
      setSession(data.access_token, {
        email: data.email,
        role: data.role,
        full_name: data.full_name,
        last_login_at: data.last_login_at,
        session_ip: data.session_ip,
      });
      router.replace("/home");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <form onSubmit={submit} className="glass w-full max-w-md space-y-5 rounded-3xl p-8" autoComplete="on">
        <div className="flex items-center gap-3">
          <img src="/logo.svg" alt="Molido" width={48} height={48} className="h-12 w-12 rounded-2xl shadow-glow" />
          <div>
            <div className="aurora text-lg font-black">Molido Trade</div>
            <div className="text-[11px] text-slate-400">ورود مالک · تک‌کاربره</div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-400">
          <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-2">
            <div>تهران</div>
            <div className="font-medium text-cyan-200">{now || "…"}</div>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-2">
            <div>حالت</div>
            <div className="font-medium text-amber-200">DEMO · Owner only</div>
          </div>
        </div>

        {ownerExists === null ? (
          <p className="text-sm text-slate-400">در حال بررسی مالک…</p>
        ) : (
          <>
            <p className="text-sm text-slate-300">
              {setup
                ? "هنوز مالکی نیست. همین یک حساب ساخته می‌شود و ثبت‌نام برای همیشه بسته می‌شود."
                : "فقط مالک سیستم می‌تواند وارد شود. حساب دومی وجود ندارد."}
            </p>

            {setup ? (
              <label className="block space-y-1 text-sm">
                <span className="text-slate-400">نام نمایشی</span>
                <input className="w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2" value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Owner" />
              </label>
            ) : null}

            <label className="block space-y-1 text-sm">
              <span className="text-slate-400">ایمیل مالک</span>
              <input className="w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2" type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>

            <label className="block space-y-1 text-sm">
              <span className="text-slate-400">رمز</span>
              <div className="flex gap-2">
                <input
                  className="w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2"
                  type={show ? "text" : "password"}
                  required
                  minLength={8}
                  autoComplete={setup ? "new-password" : "current-password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyUp={(e) => setCaps(e.getModifierState("CapsLock"))}
                />
                <button type="button" className="rounded-xl border border-white/10 px-3 text-xs text-slate-300" onClick={() => setShow((s) => !s)}>
                  {show ? "پنهان" : "نمایش"}
                </button>
              </div>
              {caps ? <span className="text-xs text-amber-300">Caps Lock روشن است</span> : null}
            </label>

            {setup ? (
              <>
                <label className="block space-y-1 text-sm">
                  <span className="text-slate-400">تکرار رمز</span>
                  <input className="w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2" type={show ? "text" : "password"} required minLength={8} autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
                </label>
                <div className="space-y-1">
                  <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
                    <div className="h-full bg-cyan-400 transition-all" style={{ width: `${(meter.n / 5) * 100}%` }} />
                  </div>
                  <p className="text-[11px] text-slate-400">قدرت رمز: {meter.label}</p>
                </div>
              </>
            ) : null}

            <button type="submit" disabled={busy || ownerExists === null} className="w-full rounded-xl bg-cyan-400/20 py-2.5 font-medium text-cyan-100 disabled:opacity-50">
              {busy ? "صبر کن…" : setup ? "ساخت مالک و ورود" : "ورود به داشبورد"}
            </button>
          </>
        )}

        {msg ? <p className="text-sm text-amber-200">{msg}</p> : null}

        <p className="text-[11px] leading-5 text-slate-500">
          هر بار آدرس سایت را بزنی دوباره لاگین می‌خواهی. رمز در مرورگر ذخیره نمی‌شود.
        </p>
      </form>
    </div>
  );
}
