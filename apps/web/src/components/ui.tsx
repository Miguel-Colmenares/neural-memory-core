"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { STATUS_LABELS, TYPE_LABELS, formatDate, label } from "@/lib/format";
import type { Memory } from "@/lib/types";

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Alert({
  kind = "error",
  children,
}: {
  kind?: "error" | "success" | "info" | "warning";
  children: ReactNode;
}) {
  const styles = {
    error: "border-red-200 bg-red-50 text-red-800",
    success: "border-emerald-200 bg-emerald-50 text-emerald-800",
    info: "border-sky-200 bg-sky-50 text-sky-800",
    warning: "border-amber-200 bg-amber-50 text-amber-900",
  }[kind];
  return (
    <div role={kind === "error" ? "alert" : "status"} className={`rounded-lg border px-4 py-3 text-sm ${styles}`}>
      {children}
    </div>
  );
}

export function Loading({ text = "Cargando…" }: { text?: string }) {
  return <p className="py-8 text-center text-sm text-slate-400">{text}</p>;
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-10 text-center text-sm text-slate-500">
      {children}
    </div>
  );
}

export function Badge({
  children,
  tone = "slate",
}: {
  children: ReactNode;
  tone?: "slate" | "blue" | "green" | "amber" | "red" | "violet";
}) {
  const tones = {
    slate: "bg-slate-100 text-slate-700",
    blue: "bg-accent-100 text-accent-600",
    green: "bg-emerald-100 text-emerald-700",
    amber: "bg-amber-100 text-amber-800",
    red: "bg-red-100 text-red-700",
    violet: "bg-violet-100 text-violet-700",
  }[tone];
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tones}`}>
      {children}
    </span>
  );
}

export function Stat({ title, value, hint }: { title: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="card">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{title}</p>
      <p className="mt-2 text-3xl font-semibold text-slate-900">{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export function Field({
  label: text,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="block">
      <span className="label">{text}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-400">{hint}</span>}
    </label>
  );
}

export function Importance({ value }: { value: number }) {
  return (
    <span title={`Importancia ${value} de 5`} className="text-xs tracking-tight text-amber-500">
      {"●".repeat(value)}
      <span className="text-slate-300">{"●".repeat(5 - value)}</span>
    </span>
  );
}

export function MemoryCard({ memory, excerpt }: { memory: Memory; excerpt?: ReactNode }) {
  return (
    <article className="card">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="blue">{label(TYPE_LABELS, memory.memory_type)}</Badge>
        {memory.kind !== "note" && <Badge tone="violet">{memory.kind}</Badge>}
        {memory.status === "archived" && <Badge tone="amber">{label(STATUS_LABELS, memory.status)}</Badge>}
        {memory.project_name && memory.project_id && (
          <Link href={`/projects/detail?id=${memory.project_id}`} className="text-xs text-slate-500 hover:underline">
            {memory.project_name}
          </Link>
        )}
        <span className="ml-auto">
          <Importance value={memory.importance} />
        </span>
      </div>
      <Link href={`/memories/detail?id=${memory.id}`} className="mt-2 block font-medium text-slate-900 hover:text-accent-600">
        {memory.title ?? memory.content.slice(0, 90)}
      </Link>
      <div className="mt-1 whitespace-pre-line text-sm text-slate-600">
        {excerpt ?? (memory.content.length > 320 ? `${memory.content.slice(0, 320)}…` : memory.content)}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400">
        <span>{formatDate(memory.created_at)}</span>
        <span>v{memory.version}</span>
        {memory.source_ref && <span title="Procedencia">Fuente: {memory.source_ref}</span>}
        {memory.tags.map((tag) => (
          <span key={tag} className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-600">
            #{tag}
          </span>
        ))}
      </div>
    </article>
  );
}

/** Convierte los marcadores **…** del resumen de búsqueda en resaltado. */
export function Highlight({ text }: { text: string }) {
  const parts = text.split("**");
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <mark key={index} className="rounded bg-yellow-100 px-0.5 text-slate-900">
            {part}
          </mark>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  );
}
