// src/lib/Api.js

export const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(
  /\/$/,
  ""
);
export const EDGE_BASE = (import.meta.env.VITE_EDGE_BASE || "").replace(
  /\/$/,
  ""
);

export function getToken() {
  return localStorage.getItem("authToken");
}
export function setToken(token) {
  localStorage.setItem("authToken", token);
}
export function clearToken() {
  localStorage.removeItem("authToken");
}

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

async function baseFetch(base, path, options = {}) {
  if (!base) {
    throw new Error(
      "Base URL kosong. Cek VITE_API_BASE / VITE_EDGE_BASE di environment Netlify."
    );
  }

  const { auth = false, headers = {}, ...rest } = options;
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

  const res = await fetch(`${base}${path}`, { ...rest, headers: finalHeaders });
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

// AUTH / DB (Railway)
export function apiFetch(path, options) {
  return baseFetch(API_BASE, path, options);
}

// CAMERA / ROI / STREAM (Edge/Laptop)
export function edgeFetch(path, options) {
  return baseFetch(EDGE_BASE, path, options);
}
