// Thin client for the backend API. All requests go to /api/* which Next.js
// proxies to FastAPI (see next.config.mjs), keeping the session cookie
// same-origin. `credentials: "include"` ensures the cookie rides along.

import type {
  NameSearchResponse,
  SuggestResponse,
  SymptomSearchResponse,
  User,
} from "@/types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(0, "Could not reach the server. Check your connection.");
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail =
      (data && typeof data.detail === "string" && data.detail) ||
      (res.status >= 500
        ? "The server had a problem. Please try again in a moment."
        : `Request failed (HTTP ${res.status}).`);
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

export function searchName(query: string): Promise<NameSearchResponse> {
  return request("/search/name", { method: "POST", body: JSON.stringify({ query }) });
}

export function suggestNames(query: string): Promise<SuggestResponse> {
  return request(`/search/suggest?q=${encodeURIComponent(query)}`, { method: "GET" });
}

export function searchSymptom(symptoms: string): Promise<SymptomSearchResponse> {
  return request("/search/symptom", {
    method: "POST",
    body: JSON.stringify({ symptoms }),
  });
}

export function me(): Promise<User> {
  return request("/auth/me", { method: "GET" });
}

export function login(username: string, password: string): Promise<User> {
  return request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function register(username: string, password: string): Promise<User> {
  return request("/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function logout(): Promise<void> {
  return request("/auth/logout", { method: "POST" });
}
