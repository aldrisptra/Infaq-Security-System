// src/lib/Api.js

// Base URL backend (ambil dari Netlify env: VITE_API_BASE)
export const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(
  /\/$/,
  ""
);

// Token helpers
export function getToken() {
  return localStorage.getItem("authToken");
}

export function setToken(token) {
  localStorage.setItem("authToken", token);
}

export function clearToken() {
  localStorage.removeItem("authToken");
}

// Response parser
async function parseBody(res) {
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return await res.json();

  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

/**
 * apiFetch("/auth/login", { method: "POST", body: ..., headers: ... })
 * apiFetch("/camera/status", { auth: true })
 *
 * options.auth = true -> otomatis pasang Authorization: Bearer <token>
 */
export async function apiFetch(path, options = {}) {
  const { auth = false, headers = {}, ...rest } = options;

  if (!API_BASE) {
    const err = new Error("VITE_API_BASE belum diset");
    err.status = 500;
    throw err;
  }

  const finalHeaders = { ...headers };

  if (auth) {
    const token = getToken();
    if (!token) {
      const err = new Error("Not authenticated");
      err.status = 401;
      throw err;
    }
    finalHeaders.Authorization = `Bearer ${token}`;
  }

  // rapihin path biar aman (boleh kirim "auth/login" atau "/auth/login")
  const cleanPath = path.startsWith("/") ? path : `/${path}`;

  const res = await fetch(`${API_BASE}${cleanPath}`, {
    ...rest,
    headers: finalHeaders,
  });

  const data = await parseBody(res);

  if (!res.ok) {
    const msg =
      data?.detail ||
      data?.message ||
      (typeof data === "string" ? data : JSON.stringify(data));

    const err = new Error(msg || "Request failed");
    err.status = res.status;
    err.data = data;
    throw err;
  }

  return data;
}
