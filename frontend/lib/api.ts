const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

// NEXT_PUBLIC_API_URL is "/api/v1" in this deployment -- correct for the
// browser, which resolves it against the page origin, but these helpers also
// run in Server Components, and fetch() on the Node side has no origin to
// resolve a relative path against, so every server-side call threw and the
// dashboard rendered "API Backend: قطع" and "Database: unknown" while the API
// was up and answering. On the server, go straight to the API service instead.
function baseFor(): string {
  if (typeof window !== "undefined") return BASE;
  if (/^https?:\/\//i.test(BASE)) return BASE;
  const internal = process.env.API_INTERNAL_URL || "http://api:8000";
  return internal.replace(/\/+$/, "") + BASE;
}

async function get(path: string) {
  try {
    const r = await fetch(`${baseFor()}${path}`, { cache: "no-store" });
    if (!r.ok) return null;
    return r.json();
  } catch {
    return null;
  }
}

export async function fetchHealth() {
  return get("/health");
}

export async function fetchSystemStatus() {
  return get("/system/status");
}

export async function fetchOpsState() {
  return get("/ops/state");
}
