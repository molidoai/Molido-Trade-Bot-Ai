"use client";

import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export function FlattenButton() {
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function flatten() {
    const token = typeof window !== "undefined" ? localStorage.getItem("molido_token") || "" : "";
    if (!token) {
      setMsg("لاگین ادمین لازم است (صفحه تنظیمات)");
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const r = await fetch(`${API}/ops/flatten`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ actor: "dashboard", reason: "dashboard flatten" }),
      });
      if (r.status === 401 || r.status === 403) {
        setMsg("فقط ادمین");
        return;
      }
      if (!r.ok) {
        setMsg("flatten ناموفق");
        return;
      }
      setMsg("درخواست flatten ارسال شد");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        disabled={busy}
        onClick={flatten}
        className="rounded-xl bg-rose-500/20 px-4 py-2 text-sm text-rose-200"
      >
        Flatten
      </button>
      {msg ? <span className="text-xs text-slate-400">{msg}</span> : null}
    </div>
  );
}
