export const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(
  /\/$/,
  ""
);
export const EDGE_BASE =
  import.meta.env.VITE_EDGE_BASE ||
  import.meta.env.VITE_API_BASE ||
  "http://127.0.0.1:8000";

const EDGE_KEY = import.meta.env.VITE_EDGE_KEY || "";

// ... getToken/setToken/clearToken tetap

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
  // parseBody dst tetap...
}

// AUTH/DB
export function apiFetch(path, options) {
  return baseFetch(API_BASE, path, options);
}

// EDGE CAMERA
export function edgeFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (EDGE_KEY) headers["X-Edge-Key"] = EDGE_KEY;
  return baseFetch(EDGE_BASE, path, { ...options, headers });
}
