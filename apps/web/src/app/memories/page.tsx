"use client";

import { useState } from "react";

import { MemoryForm } from "@/components/MemoryForm";
import { Alert, Empty, Field, Loading, MemoryCard, PageHeader } from "@/components/ui";
import { query } from "@/lib/api";
import { TYPE_LABELS } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { MemoryList, Project } from "@/lib/types";

const PAGE = 20;

export default function MemoriesPage() {
  const projects = useApi<Project[]>("/projects");
  const tags = useApi<{ tag: string; count: number }[]>("/memories/tags");
  const [showForm, setShowForm] = useState(false);
  const [memoryType, setMemoryType] = useState("");
  const [projectId, setProjectId] = useState("");
  const [tag, setTag] = useState("");
  const [status, setStatus] = useState("active");
  const [order, setOrder] = useState("created_desc");
  const [offset, setOffset] = useState(0);

  const path = `/memories${query({ memory_type: memoryType, project_id: projectId, tag, status, order, limit: PAGE, offset })}`;
  const list = useApi<MemoryList>(path);
  const change = (setter: (value: string) => void) => (value: string) => {
    setter(value);
    setOffset(0);
  };

  return (
    <>
      <PageHeader
        title="Explorador de recuerdos"
        subtitle="Todo lo que el sistema recuerda, con su tipo, procedencia, etiquetas e historial."
        actions={<button className="btn-primary" onClick={() => setShowForm((v) => !v)}>{showForm ? "Cerrar formulario" : "Nuevo recuerdo"}</button>}
      />
      {showForm && (
        <div className="mb-6">
          <MemoryForm projects={projects.data ?? []} onCreated={() => { void list.reload(); void tags.reload(); }} />
        </div>
      )}
      <div className="card mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Field label="Tipo">
          <select className="input" value={memoryType} onChange={(e) => change(setMemoryType)(e.target.value)}>
            <option value="">Todos</option>
            {Object.entries(TYPE_LABELS).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
          </select>
        </Field>
        <Field label="Proyecto">
          <select className="input" value={projectId} onChange={(e) => change(setProjectId)(e.target.value)}>
            <option value="">Todos</option>
            {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <Field label="Etiqueta">
          <select className="input" value={tag} onChange={(e) => change(setTag)(e.target.value)}>
            <option value="">Todas</option>
            {tags.data?.map((t) => <option key={t.tag} value={t.tag}>{t.tag} ({t.count})</option>)}
          </select>
        </Field>
        <Field label="Estado">
          <select className="input" value={status} onChange={(e) => change(setStatus)(e.target.value)}>
            <option value="active">Activos</option>
            <option value="archived">Archivados</option>
            <option value="any">Todos</option>
          </select>
        </Field>
        <Field label="Orden">
          <select className="input" value={order} onChange={(e) => change(setOrder)(e.target.value)}>
            <option value="created_desc">Más recientes</option>
            <option value="created_asc">Más antiguos</option>
            <option value="updated_desc">Última modificación</option>
            <option value="importance_desc">Más importantes</option>
          </select>
        </Field>
      </div>
      {list.error && <Alert>{list.error}</Alert>}
      {list.loading && !list.data && <Loading />}
      {list.data && (
        <>
          <p className="mb-3 text-xs text-slate-500">{list.data.total} recuerdo(s)</p>
          {list.data.items.length === 0 ? (
            <Empty>No hay recuerdos con estos filtros.</Empty>
          ) : (
            <div className="space-y-3">{list.data.items.map((memory) => <MemoryCard key={memory.id} memory={memory} />)}</div>
          )}
          <div className="mt-4 flex items-center justify-between">
            <button className="btn-secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Anteriores</button>
            <span className="text-xs text-slate-500">
              {list.data.total === 0 ? 0 : offset + 1}–{Math.min(offset + PAGE, list.data.total)} de {list.data.total}
            </span>
            <button className="btn-secondary" disabled={offset + PAGE >= list.data.total} onClick={() => setOffset(offset + PAGE)}>Siguientes</button>
          </div>
        </>
      )}
    </>
  );
}
