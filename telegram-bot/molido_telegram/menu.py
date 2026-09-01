"""Inline-keyboard menu: every view reachable by tapping, not typing.

Commands still work, but nobody should have to remember them. Each screen
returns (text, keyboard) so the same builder serves both a /command and a
button callback.

Read-only views are open to any allowed chat. Anything that changes trading
state stays admin-only and keeps its confirmation step -- a button must not be
an easier path to going live than the dashboard is.
"""

from __future__ import annotations

from typing import Any

from molido_telegram import live_data as ld


def kb(rows: list[list[tuple[str, str]]]) -> dict:
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}


MAIN_KB = kb([
    [("📊 وضعیت", "v:status"), ("💰 موجودی", "v:balance")],
    [("📈 پوزیشن‌ها", "v:positions"), ("🧠 مغزها", "v:brains")],
    [("🔍 چرا معامله نمی‌کند؟", "v:why")],
    [("⚙️ ریسک", "v:risk"), ("🎯 نمادها", "v:symbols")],
    [("👥 حساب‌ها", "v:accounts"), ("📜 ژورنال", "v:journal")],
    [("🔄 تازه‌سازی", "v:menu"), ("🛑 کنترل", "v:control")],
])

CONTROL_KB = kb([
    [("⏸ توقف ورود جدید", "c:pause"), ("▶️ ازسرگیری", "c:resume")],
    [("🔻 بستن همه پوزیشن‌ها", "c:flatten")],
    [("⛔️ خاموش کردن مستر", "c:stop")],
    [("⬅️ بازگشت", "v:menu")],
])

BACK_KB = kb([[("⬅️ منو", "v:menu")]])


def _fresh(p: dict) -> str:
    age = ld.age_seconds(p.get("as_of"))
    if age is None:
        return "نامشخص"
    if age < 90:
        return f"زنده ({ld.tehran(p.get('as_of'))})"
    return f"⚠️ کهنه — {int(age // 60)} دقیقه پیش"


def view_menu() -> tuple[str, dict]:
    ps = ld.all_portfolios()
    eq = sum(float(p.get("equity") or 0) for p in ps)
    pos = sum(int(p.get("open_positions") or 0) for p in ps)
    master = any(p.get("master_on") for p in ps)
    text = (
        "<b>🤖 Molido Trade</b>\n"
        f"مستر: {'🟢 روشن' if master else '🔴 خاموش'}  |  حساب‌ها: {len(ps) or 1}\n"
        f"اکوئیتی کل: <b>${ld.money(eq)}</b>  |  پوزیشن باز: <b>{pos}</b>\n\n"
        "یکی را انتخاب کن:"
    )
    return text, MAIN_KB


def view_status() -> tuple[str, dict]:
    ps = ld.all_portfolios()
    if not ps:
        return "هنوز عکس‌برداری از حساب انجام نشده. موتور باید یک چرخه کامل بزند.", BACK_KB
    out = ["<b>📊 وضعیت</b>"]
    for p in ps:
        out += [
            f"\n<b>{p.get('account_name') or p.get('account_id')}</b>  ({p.get('account_mode', '—')})",
            f"مستر: {'🟢 روشن' if p.get('master_on') else '🔴 خاموش'}",
            f"سشن: {p.get('session_note') or '—'}",
            f"اکوئیتی: ${ld.money(p.get('equity'))}  |  موجودی: ${ld.money(p.get('balance'))}",
            f"پوزیشن باز: {p.get('open_positions', 0)}  |  دراودان: {ld.money(p.get('drawdown_pct'))}٪",
            f"داده: {_fresh(p)}",
        ]
    return "\n".join(out), BACK_KB


def view_balance() -> tuple[str, dict]:
    ps = ld.all_portfolios()
    if not ps:
        return "داده‌ای در دسترس نیست.", BACK_KB
    out = ["<b>💰 موجودی</b>"]
    tb = te = tf = 0.0
    for p in ps:
        bal = float(p.get("balance") or 0)
        eq = float(p.get("equity") or 0)
        fl = float(p.get("unrealized_pnl") or 0)
        tb += bal
        te += eq
        tf += fl
        out += [
            f"\n<b>{p.get('account_name') or p.get('account_id')}</b>",
            f"موجودی: ${ld.money(bal)}",
            f"اکوئیتی: ${ld.money(eq)}",
            f"سود شناور: {'+' if fl >= 0 else ''}{ld.money(fl)}$",
            f"مارجین آزاد: ${ld.money(p.get('free_margin'))}",
        ]
    if len(ps) > 1:
        out += ["", f"<b>جمع:</b> موجودی ${ld.money(tb)} | اکوئیتی ${ld.money(te)} | شناور {ld.money(tf)}$"]
    out += ["", "<i>موجودی = سود تحقق‌یافته. اکوئیتی شامل پوزیشن‌های باز هم هست.</i>"]
    return "\n".join(out), BACK_KB


def view_positions() -> tuple[str, dict]:
    ps = ld.all_portfolios()
    rows = [(p, x) for p in ps for x in (p.get("positions") or [])]
    if not rows:
        return "<b>📈 پوزیشن‌ها</b>\n\nهیچ پوزیشن بازی وجود ندارد.", BACK_KB
    out = ["<b>📈 پوزیشن‌های باز</b>"]
    for p, x in rows:
        pnl = float(x.get("profit") or x.get("unrealized_pnl") or 0)
        out += [
            f"\n<b>{x.get('symbol')}</b> {x.get('side')}  {x.get('volume')} لات",
            f"ورود: {x.get('price_open') or x.get('entry_price')}  |  حد ضرر: {x.get('sl') or x.get('stop_loss') or '—'}",
            f"سود/زیان: {'🟢 +' if pnl >= 0 else '🔴 '}{ld.money(pnl)}$",
        ]
    return "\n".join(out), BACK_KB


def view_why() -> tuple[str, dict]:
    out = ["<b>🔍 چرا معامله نمی‌کند؟</b>", "<i>بر پایه‌ی آخرین ۴۰۰ تصمیم واقعی</i>"]
    found = False
    for aid in ld.account_ids():
        rows = ld.blockers(aid)
        if not rows:
            continue
        found = True
        total = sum(v for _, v in rows)
        out.append(f"\n<b>{aid}</b>")
        for name, count in rows[:7]:
            out.append(f"  {100 * count / total:4.1f}٪  ({count})  {name}")
    if not found:
        return "هنوز تصمیمی ثبت نشده.", BACK_KB
    out += ["", "<i>«ستاپ معتبری نیست» طبیعی است — ربات فقط وقتی شرایط جور باشد وارد می‌شود.</i>"]
    return "\n".join(out), BACK_KB


def view_brains() -> tuple[str, dict]:
    out = ["<b>🧠 سه مغز — آخرین تصمیم‌ها</b>"]
    names = {"setup": "مغز۱ ستاپ", "edge": "مغز۲ لبه", "survival": "مغز۳ بقا"}
    found = False
    for aid in ld.account_ids():
        for d in ld.brain_decisions(aid, 4):
            found = True
            ok = d.get("allow")
            out.append(
                f"\n{'✅' if ok else '⛔️'} <b>{d.get('symbol')}</b> {d.get('side') or ''}"
                f"  {ld.tehran(d.get('ts'))}"
            )
            for b in d.get("brains") or []:
                mark = "✅" if b.get("allow") and (b.get("size_mult") or 0) > 0 else "⛔️"
                out.append(f"   {mark} {names.get(b.get('name'), b.get('name'))} × {b.get('size_mult')}")
            if d.get("p_win") is not None:
                out.append(f"   احتمال برد: {d.get('p_win')}  |  بازده مورد انتظار: {d.get('expected_r')}R")
            if d.get("skipped_reason"):
                out.append(f"   دلیل رد: {str(d.get('skipped_reason'))[:70]}")
    if not found:
        return "هنوز تصمیم مغزی ثبت نشده.", BACK_KB
    out += ["", "<i>هر مغز فقط می‌تواند وتو کند یا حجم را کم کند — هرگز بزرگ‌تر نمی‌کند.</i>"]
    return "\n".join(out), BACK_KB


def view_risk() -> tuple[str, dict]:
    s = ld.settings()
    bal = 0.0
    for p in ld.all_portfolios():
        bal += float(p.get("balance") or 0)
    rpt = float(s.get("default_risk_per_trade") or 0)
    dl = float(s.get("max_daily_loss") or 0)
    out = [
        "<b>⚙️ محدودیت‌های ریسک</b>",
        f"ریسک هر معامله: {rpt * 100:.2f}٪" + (f"  (≈ ${ld.money(bal * rpt)})" if bal else ""),
        f"سقف ضرر روزانه: {dl * 100:.2f}٪" + (f"  (≈ ${ld.money(bal * dl)})" if bal else ""),
        f"سقف ضرر هفتگی: {float(s.get('max_weekly_loss') or 0) * 100:.2f}٪",
        f"حداکثر دراودان: {float(s.get('max_drawdown') or 0) * 100:.2f}٪",
        f"حداکثر پوزیشن باز: {s.get('max_open_positions', '—')}",
        f"حداکثر ورود روزانه: {s.get('max_entries_per_day', '—')}",
    ]
    if rpt and dl and rpt >= dl:
        out += ["", "⚠️ <b>ریسک هر معامله برابر یا بیش از سقف روزانه است</b> — اولین معامله‌ی بازنده کل روز را متوقف می‌کند."]
    return "\n".join(out), BACK_KB


def view_symbols() -> tuple[str, dict]:
    s = ld.settings()
    syms = [x.strip() for x in str(s.get("symbols") or "auto").split(",") if x.strip()]
    out = ["<b>🎯 نمادها</b>", "<i>ترتیب = اولویت</i>", ""]
    for i, sym in enumerate(syms):
        tag = " ⭐ اولویت ۱" if i == 0 else (" ⭐ اولویت ۲" if i == 1 else "")
        out.append(f"{i + 1}. <b>{sym}</b>{tag}")
    tf = s.get("timeframe") or "auto"
    out += [
        "",
        f"تایم‌فریم: <b>{tf}</b>" + ("  (جاروب M15 و M5)" if str(tf).lower() in ("auto", "") else ""),
        f"استراتژی‌ها: {', '.join(s.get('strategy_names') or []) or '—'}",
        f"فقط همپوشانی لندن/نیویورک: {'بله' if s.get('session_overlap_only') else 'خیر — همه‌ی سشن‌ها'}",
    ]
    return "\n".join(out), BACK_KB


def view_accounts() -> tuple[str, dict]:
    s = ld.settings()
    accounts = s.get("accounts")
    out = ["<b>👥 حساب‌ها</b>"]
    if not isinstance(accounts, list) or not accounts:
        out += [
            "",
            "فقط یک حساب (default) از تنظیمات اصلی فعال است.",
            f"لاگین: {s.get('mt5_login') or '—'}  |  سرور: {s.get('mt5_server') or '—'}",
            f"حالت: {s.get('trading_account_mode', 'DEMO')}",
            "",
            "<i>افزودن حساب از صفحه‌ی «حساب‌ها» در داشبورد.</i>",
        ]
        return "\n".join(out), BACK_KB
    for a in accounts:
        if not isinstance(a, dict):
            continue
        floor = float(a.get("prop_initial_balance") or 0) * (1 - float(a.get("prop_max_loss_pct") or 0.10))
        out += [
            f"\n<b>{a.get('name') or a.get('id')}</b>  ({a.get('trading_account_mode', 'DEMO')})",
            f"وضعیت: {'🟢 فعال' if a.get('enabled') else '⚪️ غیرفعال'}",
            f"لاگین: {a.get('mt5_login') or '—'}  |  پورت: {a.get('rpc_port') or '—'}",
        ]
        if floor > 0:
            out.append(f"کف پراپ: زیر ${ld.money(floor)} معامله نمی‌کند")
    return "\n".join(out), BACK_KB


def view_journal() -> tuple[str, dict]:
    out = ["<b>📜 آخرین رویدادها</b>"]
    rows = [d for d in ld.journal_lines("default", 200) if d.get("event") != "open_mark"][-12:]
    if not rows:
        return "ژورنال خالی است.", BACK_KB
    icon = {"fill": "✅", "accept": "📨", "veto": "⛔️", "skip": "⏭", "flatten": "🔻"}
    for d in rows:
        out.append(
            f"{icon.get(d.get('event'), '•')} {ld.tehran(d.get('ts'))} "
            f"<b>{d.get('symbol') or ''}</b> {str(d.get('reason') or d.get('event'))[:52]}"
        )
    return "\n".join(out), BACK_KB


VIEWS = {
    "menu": view_menu,
    "status": view_status,
    "balance": view_balance,
    "positions": view_positions,
    "why": view_why,
    "brains": view_brains,
    "risk": view_risk,
    "symbols": view_symbols,
    "accounts": view_accounts,
    "journal": view_journal,
}


def render(name: str) -> tuple[str, dict]:
    fn = VIEWS.get(name)
    if fn is None:
        return view_menu()
    try:
        return fn()
    except Exception as exc:  # never let a bad file kill the reply
        return f"خطا در خواندن داده: {type(exc).__name__}", BACK_KB


def confirm_kb(action: str) -> dict:
    return kb([[("✅ بله، انجام بده", f"k:{action}"), ("❌ انصراف", "v:menu")]])


CONTROL_LABELS: dict[str, str] = {
    "pause": "توقف ورودهای جدید",
    "resume": "ازسرگیری معاملات",
    "flatten": "بستن همه‌ی پوزیشن‌ها",
    "stop": "خاموش کردن مستر",
}


CONTROL_TEXT = (
    "<b>🛑 کنترل</b>\n\n"
    "یک عمل را انتخاب کن — قبل از اجرا تأیید گرفته می‌شود."
)


def confirm_text(action: str) -> str:
    """Name the action before doing it, so a mis-tap is recoverable."""
    label = CONTROL_LABELS.get(action, action)
    return (
        "<b>تأیید می‌کنی؟</b>\n\n"
        f"{label}\n\n"
        "این عمل روی حساب زنده اثر دارد."
    )


# --- Reply keyboard -------------------------------------------------------
# The persistent keyboard that sits under the message box, rather than glass
# buttons attached to one message. It stays put, it is thumb-sized, and it
# does not scroll away up the chat -- for something checked many times a day
# that matters more than looking tidy.
#
# These send ordinary text, so every screen is reachable by tapping AND by
# typing, and older clients that ignore keyboards still work.

BTN = {
    "📊 وضعیت": "status",
    "💰 موجودی": "balance",
    "📈 پوزیشن‌ها": "positions",
    "🧠 مغزها": "brains",
    "🔍 چرا معامله نمی‌کند؟": "why",
    "⚙️ ریسک": "risk",
    "🎯 نمادها": "symbols",
    "👥 حساب‌ها": "accounts",
    "📜 ژورنال": "journal",
    "🔄 منو": "menu",
    "🛑 کنترل": "control",
}

REPLY_KB = {
    "keyboard": [
        ["📊 وضعیت", "💰 موجودی"],
        ["📈 پوزیشن‌ها", "🧠 مغزها"],
        ["🔍 چرا معامله نمی‌کند؟"],
        ["⚙️ ریسک", "🎯 نمادها"],
        ["👥 حساب‌ها", "📜 ژورنال"],
        ["🔄 منو", "🛑 کنترل"],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
    "input_field_placeholder": "یک دکمه بزن",
}


def view_for_text(text: str) -> str | None:
    """Map a tapped keyboard button (or typed text) to a view name."""
    t = (text or "").strip()
    if t in BTN:
        return BTN[t]
    # Tolerate a missing or different emoji: match on the words.
    bare = "".join(ch for ch in t if ch.isalpha() or ch.isspace() or ch == "‌").strip()
    for label, view in BTN.items():
        lb = "".join(ch for ch in label if ch.isalpha() or ch.isspace() or ch == "‌").strip()
        if bare and bare == lb:
            return view
    return None
