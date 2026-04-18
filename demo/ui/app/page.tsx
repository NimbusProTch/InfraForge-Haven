"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { demoApi, API_URL, type Note, type Stats } from "../lib/api";

export default function HomePage() {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const notes = useQuery<Note[], Error>({
    queryKey: ["notes"],
    queryFn: () => demoApi.listNotes(),
  });

  const stats = useQuery<Stats, Error>({
    queryKey: ["stats"],
    queryFn: () => demoApi.stats(),
    refetchInterval: 3000,
  });

  const createMut = useMutation({
    mutationFn: () => demoApi.createNote(title, body),
    onSuccess: () => {
      setTitle("");
      setBody("");
      setErr(null);
      qc.invalidateQueries({ queryKey: ["notes"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (e: Error) => setErr(e.message),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => demoApi.deleteNote(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notes"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });

  return (
    <main className="mx-auto max-w-3xl p-6">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-white">iyziops Demo — Notes</h1>
        <p className="mt-1 text-sm text-slate-400">
          Postgres + Redis + RabbitMQ • deployed via the iyziops platform
        </p>
      </header>

      {/* Stats bar */}
      {stats.data && (
        <section className="mb-6 grid grid-cols-2 gap-3 rounded-lg border border-slate-700 bg-slate-900/50 p-4 text-sm md:grid-cols-5">
          <div><div className="text-slate-400">notes in DB</div><div className="text-lg font-semibold text-white">{stats.data.notes_in_db}</div></div>
          <div><div className="text-slate-400">redis hits</div><div className="text-lg font-semibold text-emerald-400">{stats.data.redis_hits}</div></div>
          <div><div className="text-slate-400">redis misses</div><div className="text-lg font-semibold text-amber-400">{stats.data.redis_misses}</div></div>
          <div><div className="text-slate-400">rmq pub</div><div className="text-lg font-semibold text-sky-400">{stats.data.rmq_published}</div></div>
          <div><div className="text-slate-400">rmq consumed</div><div className="text-lg font-semibold text-fuchsia-400">{stats.data.rmq_consumed}</div></div>
        </section>
      )}

      {/* Create form */}
      <section className="mb-8 rounded-lg border border-slate-700 bg-slate-900/50 p-4">
        <h2 className="mb-3 font-semibold text-white">Create note</h2>
        <input
          className="mb-2 w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 text-white placeholder-slate-500 focus:border-sky-500 focus:outline-none"
          placeholder="Title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={createMut.isPending}
        />
        <textarea
          className="mb-2 w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 text-white placeholder-slate-500 focus:border-sky-500 focus:outline-none"
          placeholder="Body"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={3}
          disabled={createMut.isPending}
        />
        <button
          className="rounded bg-sky-600 px-4 py-2 font-semibold text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:bg-slate-700"
          onClick={() => createMut.mutate()}
          disabled={createMut.isPending || !title.trim() || !body.trim()}
        >
          {createMut.isPending ? "Creating…" : "Create"}
        </button>
        {err && <p className="mt-2 text-sm text-red-400">⚠️ {err}</p>}
      </section>

      {/* Notes list */}
      <section>
        <h2 className="mb-3 font-semibold text-white">Notes ({notes.data?.length ?? 0})</h2>
        {notes.isLoading && <p className="text-slate-400">Loading…</p>}
        {notes.error && (
          <p className="rounded border border-red-500/50 bg-red-900/30 p-3 text-sm text-red-300">
            Failed to reach API: {notes.error.message}
          </p>
        )}
        <ul className="space-y-2">
          {notes.data?.map((n) => (
            <li
              key={n.id}
              className="flex items-start justify-between rounded border border-slate-700 bg-slate-900/50 p-3"
            >
              <div className="min-w-0 flex-1">
                <div className="font-medium text-white">{n.title}</div>
                <div className="mt-1 truncate text-sm text-slate-400">{n.body}</div>
                {n.created_at && (
                  <div className="mt-1 text-xs text-slate-500">{n.created_at}</div>
                )}
              </div>
              <button
                className="ml-3 text-xs text-slate-500 hover:text-red-400"
                onClick={() => deleteMut.mutate(n.id)}
                disabled={deleteMut.isPending}
              >
                delete
              </button>
            </li>
          ))}
        </ul>
      </section>

      <footer className="mt-10 border-t border-slate-800 pt-6 text-center text-xs text-slate-500">
        <p>
          API: <a href={API_URL} className="text-sky-400 hover:underline" target="_blank" rel="noreferrer">{API_URL}</a>
        </p>
        <p className="mt-1">🚀 Deployed via iyziops platform — tenant: demo, services: demo-pg + demo-cache + demo-queue</p>
      </footer>
    </main>
  );
}
