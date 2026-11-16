"use client";

import Link from "next/link";

import { Alert, Empty, Loading, PageHeader, Stat } from "@/components/ui";
import { ACTION_LABELS, SOURCE_LABELS, STATUS_LABELS, TYPE_LABELS, formatDate, label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { ChangeEntry, Stats } from "@/lib/types";

function Breakdown({ title, data, labels }: { title: string; data: Record<string, number>; labels: Record<string, string> }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, count]) => count));
  return (
    <div className="card">
      <h2>{title}</h2>
      {entries.length === 0 ? (
        <p className="mt-3 text-sm text-slate-400">Sin datos todavía.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {entries.map(([key, count]) => (
            <li key={key} className="text-sm">
              <div className="flex justify-between">
                <span>{label(labels, key)}</span>
                <span className="font-medium text-slate-900">{count}</span>
              </div>
              <div className="mt-1 h-1.5 rounded bg-slate-100">
                <div className="h-1.5 rounded bg-accent-500" style={{ width: `${(count / max) * 100}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const stats = useApi<Stats>("/stats");
  const history = useApi<{ items: ChangeEntry[] }>("/history?limit=8");

  if (stats.loading) return <Loading />;
  if (stats.error || !stats.data) return <Alert>{stats.error ?? "Sin datos."}</Alert>;
  const s = stats.data;
  const tasks = s.modules.tasks as { open?: number; total?: number } | undefined;

  return (
    <>
      <PageHeader
        title="Panel"
        subtitle={`Indicadores calculados desde la base de datos el ${formatDate(s.generated_at)}.`}
        actions={
          <button className="btn-secondary" onClick={() => { void stats.reload(); void history.reload(); }}>
            Actualizar
          </button>
        }
      />
      {s.memories.total === 0 && (
        <div className="mb-6">
          <Empty>
            Tu memoria está vacía. <Link className="link" href="/memories">Crea tu primer recuerdo</Link> o{" "}
            <Link className="link" href="/projects">un proyecto</Link>.
          </Empty>
        </div>
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat title="Recuerdos" value={s.memories.total} hint={`${s.memories.created_last_7_days} en los últimos 7 días`} />
        <Stat title="Proyectos" value={s.projects.total} hint={`${s.projects.by_status.active ?? 0} activos`} />
        <Stat title="Relaciones" value={s.relations} hint="Enlaces entre recuerdos" />
        <Stat title="Versiones guardadas" value={s.versions} hint={`${s.changes.total} cambios registrados`} />
        <Stat title="Tareas abiertas" value={tasks?.open ?? "—"} hint={tasks ? `${tasks.total ?? 0} en total` : "Módulo de tareas inactivo"} />
        <Stat
          title="Índice vectorial"
          value={`${s.index.memories_indexed}/${s.index.memories_total}`}
          hint={s.index.memories_pending > 0 ? `${s.index.memories_pending} pendientes de indexar` : "Todo indexado"}
        />
        <Stat title="Último recuerdo" value={<span className="text-lg">{formatDate(s.memories.last_created_at)}</span>} />
        <Stat title="Último cambio" value={<span className="text-lg">{formatDate(s.changes.last_at)}</span>} hint={`${s.changes.last_7_days} cambios en 7 días`} />
      </div>
      {s.index.memories_pending > 0 && (
        <div className="mt-4">
          <Alert kind="warning">
            Hay {s.index.memories_pending} recuerdos sin embeddings: no aparecerán en la búsqueda semántica.
            Reindexa desde <Link className="link" href="/settings">Proveedores de IA</Link>.
          </Alert>
        </div>
      )}
      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Breakdown title="Por tipo de memoria" data={s.memories.by_type} labels={TYPE_LABELS} />
        <Breakdown title="Por procedencia" data={s.memories.by_source} labels={SOURCE_LABELS} />
        <Breakdown title="Por estado" data={s.memories.by_status} labels={STATUS_LABELS} />
      </div>
      <div className="card mt-6">
        <div className="flex items-center justify-between">
          <h2>Actividad reciente</h2>
          <Link href="/history" className="link text-sm">Ver historial completo</Link>
        </div>
        {history.error && <div className="mt-3"><Alert>{history.error}</Alert></div>}
        {history.data && history.data.items.length === 0 && <p className="mt-3 text-sm text-slate-400">Sin actividad todavía.</p>}
        <ul className="mt-3 divide-y divide-slate-100">
          {history.data?.items.map((entry) => (
            <li key={entry.id} className="flex flex-wrap items-baseline gap-x-3 py-2 text-sm">
              <span className="w-36 shrink-0 text-xs text-slate-400">{formatDate(entry.created_at)}</span>
              <span className="w-28 shrink-0 text-xs font-medium text-slate-500">{label(ACTION_LABELS, entry.action)}</span>
              <span className="min-w-0 flex-1 truncate">{entry.summary}</span>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
