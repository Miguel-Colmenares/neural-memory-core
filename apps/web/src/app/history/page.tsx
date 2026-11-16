"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Empty, Field, Loading, PageHeader } from "@/components/ui";
import { query } from "@/lib/api";
import { ACTION_LABELS, formatDate, label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { ChangeEntry } from "@/lib/types";

const PAGE = 40;
const ENTITY_LABELS: Record<string, string> = {
  memory: "Recuerdo",
  project: "Proyecto",
  project_relation: "Relación de proyectos",
  relation: "Relación",
  task: "Tarea",
  user: "Usuario",
  system: "Sistema",
};

function entityHref(entry: ChangeEntry): string | null {
  if (entry.action === "delete") return null;
  if (entry.entity_type === "memory") return `/memories/detail?id=${entry.entity_id}`;
  if (entry.entity_type === "project") return `/projects/detail?id=${entry.entity_id}`;
  return null;
}

export default function HistoryPage() {
  const [entityType, setEntityType] = useState("");
  const [action, setAction] = useState("");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<number | null>(null);
  const history = useApi<{ items: ChangeEntry[]; total: number }>(
    `/history${query({ entity_type: entityType, action, limit: PAGE, offset })}`,
  );

  return (
    <>
      <PageHeader title="Historial de actualizaciones" subtitle="Registro de todo lo que cambia en el sistema: quién, qué y cuándo." />
      <div className="card mb-4 grid gap-3 sm:grid-cols-3">
        <Field label="Elemento">
          <select className="input" value={entityType} onChange={(e) => { setEntityType(e.target.value); setOffset(0); }}>
            <option value="">Todos</option>
            {Object.entries(ENTITY_LABELS).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
          </select>
        </Field>
        <Field label="Acción">
          <select className="input" value={action} onChange={(e) => { setAction(e.target.value); setOffset(0); }}>
            <option value="">Todas</option>
            {Object.entries(ACTION_LABELS).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
          </select>
        </Field>
      </div>
      {history.error && <Alert>{history.error}</Alert>}
      {history.loading && !history.data && <Loading />}
      {history.data && history.data.items.length === 0 && <Empty>No hay cambios registrados con estos filtros.</Empty>}
      {history.data && history.data.items.length > 0 && (
        <>
          <ul className="card divide-y divide-slate-100 p-0">
            {history.data.items.map((entry) => {
              const href = entityHref(entry);
              return (
                <li key={entry.id} className="px-4 py-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="w-36 shrink-0 text-xs text-slate-400">{formatDate(entry.created_at)}</span>
                    <Badge>{label(ENTITY_LABELS, entry.entity_type)}</Badge>
                    <Badge tone={entry.action === "delete" ? "red" : "blue"}>{label(ACTION_LABELS, entry.action)}</Badge>
                    <span className="min-w-0 flex-1">{href ? <Link className="hover:underline" href={href}>{entry.summary}</Link> : entry.summary}</span>
                    <span className="text-xs text-slate-400">{entry.actor ?? "sistema"}</span>
                    {Object.keys(entry.details).length > 0 && (
                      <button className="text-xs text-accent-600 hover:underline" onClick={() => setOpen(open === entry.id ? null : entry.id)}>
                        {open === entry.id ? "Ocultar" : "Detalles"}
                      </button>
                    )}
                  </div>
                  {open === entry.id && <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-3 text-xs">{JSON.stringify(entry.details, null, 2)}</pre>}
                </li>
              );
            })}
          </ul>
          <div className="mt-4 flex items-center justify-between">
            <button className="btn-secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Más recientes</button>
            <span className="text-xs text-slate-500">{offset + 1}–{Math.min(offset + PAGE, history.data.total)} de {history.data.total}</span>
            <button className="btn-secondary" disabled={offset + PAGE >= history.data.total} onClick={() => setOffset(offset + PAGE)}>Más antiguos</button>
          </div>
        </>
      )}
    </>
  );
}
