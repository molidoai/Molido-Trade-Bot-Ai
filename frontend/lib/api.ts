const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

async function get(path: string) {
  try {
    const r = await fetch(`${BASE}${path}`, { cache: "no-store" });
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
