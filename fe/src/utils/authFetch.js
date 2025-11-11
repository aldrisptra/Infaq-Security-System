const LS_KEY = "infaq_auth_v1";

export function authFetch(input, init = {}) {
  const raw = localStorage.getItem(LS_KEY);
  let token = null;
  try {
    token = raw ? JSON.parse(raw).token : null;
  } catch {}

  const headers = new Headers(init.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);

  return fetch(input, { ...init, headers });
}
