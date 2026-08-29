const KEY = "molido_owner_token";
const META = "molido_owner_meta";

export type OwnerMeta = {
  email?: string;
  role?: string;
  full_name?: string | null;
  last_login_at?: string | null;
  session_ip?: string | null;
};

export function getToken(): string {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem(KEY) || "";
}

export function getMeta(): OwnerMeta {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(sessionStorage.getItem(META) || "{}");
  } catch {
    return {};
  }
}

export function setSession(token: string, meta: OwnerMeta) {
  sessionStorage.setItem(KEY, token);
  sessionStorage.setItem(META, JSON.stringify(meta));
}

export function clearSession() {
  sessionStorage.removeItem(KEY);
  sessionStorage.removeItem(META);
}

export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
