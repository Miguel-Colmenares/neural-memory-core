"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";

import { Alert, Badge, Field, Importance, Loading, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { SOURCE_LABELS, STATUS_LABELS, TYPE_LABELS, formatDate, label, splitTags } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Memory, MemoryVersion, Neighbor, Project } from "@/lib/types";

const RELATION_TYPES = ["related", "contradicts", "supersedes", "derived_from", "part_of", "references"];
const CHANGE_LABELS: Record<string, string> = {
  create: "Creación",
  update: "Actualización",
  correction: "Corrección manual",
  archive: "Archivado",
  restore: "Reactivación",
  revert: "Reversión",
};

function Detail() {
  const id = useSearchParams().get("id");
  const router = useRouter();
  const memory = useApi<Memory>(id ? `/memories/${id}` : null);
  const versions = useApi<MemoryVersion[]>(id ? `/memories/${id}/versions` : null);
  const relations = useApi<Neighbor[]>(id ? `/memories/${id}/relations` : null);
  const projects = useApi<Project[]>("/projects");
  const { busy, error, notice, run } = useAction();

  const [editing, setEditing] = useState(false);
  const [content, setContent] = useState("");
  const [title, setTitle] = useState("");
  const [memoryType, setMemoryType] = useState("semantic");
  const [projectId, setProjectId] = useState("");
  const [tags, setTags] = useState("");
  const [importance, setImportance] = useState(3);
  const [reason, setReason] = useState("");
  const [correction, setCorrection] = useState(false);
  const [targetId, setTargetId] = useState("");
  const [relationType, setRelationType] = useState("related");
  const [openVersion, setOpenVersion] = useState<number | null>(null);

  const current = memory.data;
  useEffect(() => {
    if (!current) return;
    setContent(current.content);
    setTitle(current.title ?? "");
    setMemoryType(current.memory_type);
    setProjectId(current.project_id ?? "");
    setTags(current.tags.join(", "));
    setImportance(current.importance);
  }, [current]);

  if (!id) return <Alert>Falta el identificador del recuerdo.</Alert>;
  if (memory.loading && !current) return <Loading />;
  if (memory.error || !current) return <Alert>{memory.error ?? "No encontrado."}</Alert>;

  const reloadAll = () => {
    void memory.reload();
    void versions.reload();
    void relations.reload();
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    const ok = await run(async () => {
      await api(`/memories/${id}`, {
        method: "PATCH",
        body: {
          content,
          title: title || null,
          memory_type: memoryType,
          project_id: projectId || null,
          tags: splitTags(tags),
          importance,
          change_reason: reason || null,
          is_correction: correction,
        },
      });
      return "Cambios guardados. La versión anterior queda en el historial.";
    });
    if (ok) {
      setEditing(false);
      setReason("");
      setCorrection(false);
      reloadAll();
    }
  };

  const act = (path: string, message: string) =>
    run(async () => {
      await api(path, { method: "POST" });
      reloadAll();
      return message;
    });

  const remove = async () => {
    if (!window.confirm("Esto elimina el recuerdo y todo su historial de forma definitiva. ¿Continuar?")) return;
    const ok = await run(async () => {
      await api(`/memories/${id}?confirm=true`, { method: "DELETE" });
    });
    if (ok) router.replace("/memories");
  };

  const addRelation = async (event: FormEvent) => {
    event.preventDefault();
    const ok = await run(async () => {
      await api("/relations", {
        method: "POST",
        body: { source_id: id, target_id: targetId.trim(), relation_type: relationType },
      });
      return "Relación creada.";
    });
    if (ok) {
      setTargetId("");
      void relations.reload();
    }
  };

  const removeRelation = (relationId: string) =>
    run(async () => {
      await api(`/relations/${relationId}`, { method: "DELETE" });
      void relations.reload();
      return "Relación eliminada.";
    });

  return (
    <>
      <PageHeader
        title={current.title ?? "Recuerdo"}
        subtitle={`Identificador: ${current.id}`}
        actions={
          <>
            <button className="btn-secondary" onClick={() => setEditing((v) => !v)}>{editing ? "Cancelar edición" : "Editar"}</button>
            {current.status === "active" ? (
              <button className="btn-secondary" disabled={busy} onClick={() => act(`/memories/${id}/archive`, "Recuerdo archivado.")}>Archivar</button>
            ) : (
              <button className="btn-secondary" disabled={busy} onClick={() => act(`/memories/${id}/restore`, "Recuerdo reactivado.")}>Reactivar</button>
            )}
            <button className="btn-danger" disabled={busy} onClick={remove}>Eliminar</button>
          </>
        }
      />
      <div className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {notice && <Alert kind="success">{notice}</Alert>}

        {editing ? (
          <form onSubmit={save} className="card space-y-4">
            <h2>Editar recuerdo</h2>
            <Field label="Contenido"><textarea className="input min-h-40" value={content} onChange={(e) => setContent(e.target.value)} required /></Field>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Título"><input className="input" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} /></Field>
              <Field label="Tipo de memoria">
                <select className="input" value={memoryType} onChange={(e) => setMemoryType(e.target.value)}>
                  {Object.entries(TYPE_LABELS).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
                </select>
              </Field>
              <Field label="Proyecto">
                <select className="input" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                  <option value="">Sin proyecto</option>
                  {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </Field>
              <Field label="Etiquetas"><input className="input" value={tags} onChange={(e) => setTags(e.target.value)} /></Field>
              <Field label={`Importancia: ${importance}`}><input type="range" min={1} max={5} value={importance} onChange={(e) => setImportance(Number(e.target.value))} className="w-full" /></Field>
              <Field label="Motivo del cambio"><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} /></Field>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={correction} onChange={(e) => setCorrection(e.target.checked)} /> Es una corrección de un dato erróneo
            </label>
            <button className="btn-primary" disabled={busy}>{busy ? "Guardando…" : "Guardar como nueva versión"}</button>
          </form>
        ) : (
          <section className="card">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="blue">{label(TYPE_LABELS, current.memory_type)}</Badge>
              <Badge tone="violet">{current.kind}</Badge>
              <Badge tone={current.status === "active" ? "green" : "amber"}>{label(STATUS_LABELS, current.status)}</Badge>
              <Importance value={current.importance} />
              <span className="text-xs text-slate-400">versión {current.version}</span>
            </div>
            <p className="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-slate-800">{current.content}</p>
            <dl className="mt-5 grid gap-x-6 gap-y-2 border-t border-slate-100 pt-4 text-sm sm:grid-cols-2">
              <div><dt className="label">Creado</dt><dd>{formatDate(current.created_at)}{current.created_by ? ` por ${current.created_by}` : ""}</dd></div>
              <div><dt className="label">Actualizado</dt><dd>{formatDate(current.updated_at)}</dd></div>
              <div><dt className="label">Fuente</dt><dd>{label(SOURCE_LABELS, current.source_type)}{current.source_ref ? ` · ${current.source_ref}` : ""}</dd></div>
              <div>
                <dt className="label">Proyecto</dt>
                <dd>{current.project_id ? <Link className="link" href={`/projects/detail?id=${current.project_id}`}>{current.project_name}</Link> : "—"}</dd>
              </div>
              <div><dt className="label">Etiquetas</dt><dd>{current.tags.length ? current.tags.map((t) => `#${t}`).join("  ") : "—"}</dd></div>
              <div><dt className="label">Módulo</dt><dd>{current.module ?? "—"}</dd></div>
              {Object.keys(current.provenance).length > 0 && (
                <div className="sm:col-span-2"><dt className="label">Procedencia detallada</dt><dd><pre className="overflow-x-auto rounded bg-slate-50 p-2 text-xs">{JSON.stringify(current.provenance, null, 2)}</pre></dd></div>
              )}
              {Object.keys(current.metadata).length > 0 && (
                <div className="sm:col-span-2"><dt className="label">Metadatos</dt><dd><pre className="overflow-x-auto rounded bg-slate-50 p-2 text-xs">{JSON.stringify(current.metadata, null, 2)}</pre></dd></div>
              )}
            </dl>
          </section>
        )}

        <section className="card">
          <h2>Relaciones</h2>
          {relations.error && <div className="mt-2"><Alert>{relations.error}</Alert></div>}
          {relations.data && relations.data.length === 0 && <p className="mt-2 text-sm text-slate-400">Sin relaciones.</p>}
          <ul className="mt-2 divide-y divide-slate-100">
            {relations.data?.map((n) => (
              <li key={n.relation.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                <Badge tone={n.relation.relation_type === "contradicts" ? "red" : "slate"}>{n.relation.relation_type}</Badge>
                <span className="text-xs text-slate-400">{n.direction === "out" ? "→" : "←"} {n.relation.origin}{n.relation.confidence !== null ? ` · ${n.relation.confidence.toFixed(2)}` : ""}</span>
                <Link className="link min-w-0 flex-1 truncate" href={`/memories/detail?id=${n.memory.id}`}>{n.memory.title ?? n.memory.content.slice(0, 100)}</Link>
                <button className="text-xs text-red-600 hover:underline" disabled={busy} onClick={() => removeRelation(n.relation.id)}>Quitar</button>
              </li>
            ))}
          </ul>
          <form onSubmit={addRelation} className="mt-3 flex flex-wrap items-end gap-2">
            <div className="min-w-64 flex-1"><Field label="Relacionar con (identificador de otro recuerdo)"><input className="input" value={targetId} onChange={(e) => setTargetId(e.target.value)} placeholder="00000000-0000-0000-0000-000000000000" required /></Field></div>
            <Field label="Tipo">
              <select className="input" value={relationType} onChange={(e) => setRelationType(e.target.value)}>
                {RELATION_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </Field>
            <button className="btn-secondary" disabled={busy || !targetId.trim()}>Añadir relación</button>
          </form>
        </section>

        <section className="card">
          <h2>Historial de versiones</h2>
          {versions.error && <div className="mt-2"><Alert>{versions.error}</Alert></div>}
          <ul className="mt-2 divide-y divide-slate-100">
            {versions.data?.map((v) => (
              <li key={v.version} className="py-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">v{v.version}</span>
                  <Badge>{CHANGE_LABELS[v.change_type] ?? v.change_type}</Badge>
                  <span className="text-xs text-slate-400">{formatDate(v.created_at)}{v.changed_by ? ` · ${v.changed_by}` : ""}</span>
                  {v.changed_fields.length > 0 && <span className="text-xs text-slate-500">Campos: {v.changed_fields.join(", ")}</span>}
                  <span className="ml-auto flex gap-3">
                    <button className="text-xs text-accent-600 hover:underline" onClick={() => setOpenVersion(openVersion === v.version ? null : v.version)}>
                      {openVersion === v.version ? "Ocultar" : "Ver contenido"}
                    </button>
                    {v.version !== current.version && (
                      <button className="text-xs text-accent-600 hover:underline" disabled={busy} onClick={() => act(`/memories/${id}/revert/${v.version}`, `Recuerdo revertido a la versión ${v.version}.`)}>
                        Volver a esta versión
                      </button>
                    )}
                  </span>
                </div>
                {v.change_reason && <p className="mt-1 text-xs text-slate-500">Motivo: {v.change_reason}</p>}
                {openVersion === v.version && <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-3 text-xs">{String(v.snapshot.content ?? "")}</pre>}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}

export default function MemoryDetailPage() {
  return (
    <Suspense fallback={<Loading />}>
      <Detail />
    </Suspense>
  );
}
