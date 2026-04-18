// Plain fetch — no auth. Demo is public.

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Note = {
  id: string;
  title: string;
  body: string;
  created_at?: string | null;
};

export type Stats = {
  notes_in_db: number;
  redis_hits: number;
  redis_misses: number;
  rmq_published: number;
  rmq_consumed: number;
  cache_hit_ratio: number;
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${body.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export const demoApi = {
  listNotes: () => req<Note[]>("/notes"),
  getNote: (id: string) => req<Note>(`/notes/${id}`),
  createNote: (title: string, body: string) =>
    req<Note>("/notes", { method: "POST", body: JSON.stringify({ title, body }) }),
  deleteNote: (id: string) => req<{ deleted: string }>(`/notes/${id}`, { method: "DELETE" }),
  stats: () => req<Stats>("/stats"),
  test: () => req<{ all_ok: boolean; checks: Record<string, { ok: boolean; error?: string }> }>("/test"),
};

export const API_URL = API;
