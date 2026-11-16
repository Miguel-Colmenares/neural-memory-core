"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";

import { MemoryForm } from "@/components/MemoryForm";
import { Alert, Badge, Field, Loading, PageHeader, Stat } from "@/components/ui";
import { api } from "@/lib/api";
import { ACTION_LABELS, STATUS_LABELS, TYPE_LABELS, formatDate, formatDay, label } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { ChangeEntry, Memory, Project, ProjectOverview, Task } from "@/lib/types";

function MemoryLinks({ title, items, empty }: { title: string; items: Memory[]; empty: string }) {
  return (
    <section className="card">
      <h2>{title}</h2>
      {items.length === 0 ? (
        <p className="mt-2 text-sm text-slate-400">{empty}</p>
      ) : (
        <ul className="mt-2 divide-y divide-slate-100">
          {items.map((m) => (
            <li key={m.id} className="py-2 text-sm">
              <Link className="link" href={`/memories/detail?id=${m.id}`}>{m.title ?? m.content.slice(0, 90)}</Link>
              <p className="line-clamp-2 text-slate-600">{m.content}</p>
              <p className="text-xs text-slate-400">{formatDate(m.updated_at)} · v{m.version}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Detail() {
  const id = useSearchParams().get("id");
  const router = useRouter();
  const overview = useApi<ProjectOverview>(id ? `/projects/${id}` : null);
  const tasks = useApi<Task[]>(id ? `/tasks?project_id=${id}` : null);
  const history = useApi<{ items: ChangeEntry[] }>(id ? `/history?project_id=${id}&limit=25` : null);
  const projects = useApi<Project[]>("/projects");
  const { busy, error, notice, run } = useAction();

  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [objectives, setObjectives] = useState("");
  const [status, setStatus] = useState("active");
  const [decision, setDecision] = useState("");
  const [decisionTitle, setDecisionTitle] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [relatedId, setRelatedId] = useState("");
  const [relationType, setRelationType] = useState("related");
  const [relationNote, setRelationNote] = useState("");
  const [showMemoryForm, setShowMemoryForm] = useState(false);

  const project = overview.data?.project;
  useEffect(() => {
    if (!project) return;
    setName(project.name);
    setDescription(project.description);
    setObjectives(project.objectives.join("\n"));
    setStatus(project.status);
  }, [project]);

  if (!id) return <Alert>Falta el identificador del proyecto.</Alert>;
  if (overview.loading && !overview.data) return <Loading />;
  if (overview.error || !overview.data || !project) return <Alert>{overview.error ?? "No encontrado."}</Alert>;
  const data = overview.data;

  const reloadAll = () => {
    void overview.reload();
    void tasks.reload();
    void history.reload();
  };
  const submit = (action: () => Promise<string | void>, after?: () => void) => async (event: FormEvent) => {
    event.preventDefault();
    if (await run(action)) {
      after?.();
      reloadAll();
    }
  };

  const save = submit(async () => {
    await api(`/projects/${id}`, {
      method: "PATCH",
      body: { name, description, status, objectives: objectives.split("\n").map((o) => o.trim()).filter(Boolean) },
    });
    return "Proyecto actualizado.";
  }, () => setEditing(false));

  const addDecision = submit(async () => {
    await api(`/projects/${id}/decisions`, { method: "POST", body: { content: decision, title: decisionTitle || null } });
    return "Decisión registrada.";
  }, () => { setDecision(""); setDecisionTitle(""); });

  const addTask = submit(async () => {
    await api("/tasks", { method: "POST", body: { title: taskTitle, project_id: id } });
  }, () => setTaskTitle(""));

  const addRelation = submit(async () => {
    await api(`/projects/${id}/relations`, {
      method: "POST",
      body: { target_project_id: relatedId, relation_type: relationType, description: relationNote },
    });
    return "Relación creada.";
  }, () => { setRelatedId(""); setRelationNote(""); });

  const setTaskStatus = (task: Task, next: string) =>
    run(async () => {
      await api(`/tasks/${task.id}`, { method: "PATCH", body: { status: next } });
      reloadAll();
    });
  const removeTask = (task: Task) =>
    run(async () => {
      await api(`/tasks/${task.id}`, { method: "DELETE" });
      reloadAll();
    });
  const removeRelation = (relationId: string) =>
    run(async () => {
      await api(`/projects/relations/${relationId}`, { method: "DELETE" });
      reloadAll();
      return "Relación eliminada.";
    });
  const remove = async () => {
    if (!window.confirm("Se eliminará el proyecto. Sus recuerdos se conservan sin proyecto asignado. ¿Continuar?")) return;
    const ok = await run(async () => {
      await api(`/projects/${id}?confirm=true`, { method: "DELETE" });
    });
    if (ok) router.replace("/projects");
  };

  const others = (projects.data ?? []).filter((p) => p.id !== id);

  return (
    <>
      <PageHeader
        title={project.name}
        subtitle={project.description || "Sin descripción."}
        actions={
          <>
            <button className="btn-secondary" onClick={() => setEditing((v) => !v)}>{editing ? "Cancelar" : "Editar"}</button>
            <button className="btn-secondary" onClick={() => setShowMemoryForm((v) => !v)}>{showMemoryForm ? "Cerrar" : "Añadir recuerdo"}</button>
            <button className="btn-danger" disabled={busy} onClick={remove}>Eliminar</button>
          </>
        }
      />
      <div className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {notice && <Alert kind="success">{notice}</Alert>}

        {editing && (
          <form onSubmit={save} className="card space-y-4">
            <h2>Editar proyecto</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Nombre"><input className="input" value={name} onChange={(e) => setName(e.target.value)} required /></Field>
              <Field label="Estado">
                <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
                  {["active", "paused", "completed", "archived"].map((s) => <option key={s} value={s}>{label(STATUS_LABELS, s)}</option>)}
                </select>
              </Field>
            </div>
            <Field label="Descripción"><textarea className="input min-h-20" value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
            <Field label="Objetivos" hint="Uno por línea."><textarea className="input min-h-20" value={objectives} onChange={(e) => setObjectives(e.target.value)} /></Field>
            <button className="btn-primary" disabled={busy}>Guardar</button>
          </form>
        )}
        {showMemoryForm && <MemoryForm projects={projects.data ?? []} defaultProjectId={id} onCreated={reloadAll} />}

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Stat title="Estado" value={<span className="text-xl">{label(STATUS_LABELS, project.status)}</span>} hint={`Creado el ${formatDay(project.created_at)}`} />
          <Stat title="Recuerdos activos" value={data.counts.active_memories} hint={`${data.counts.archived_memories} archivados`} />
          <Stat title="Decisiones" value={data.counts.by_type.project ?? 0} hint="Memoria de proyecto" />
          <Stat title="Tareas abiertas" value={tasks.data ? tasks.data.filter((t) => t.status === "pending" || t.status === "in_progress").length : "—"} />
        </div>

        <section className="card">
          <h2>Objetivos</h2>
          {project.objectives.length === 0 ? <p className="mt-2 text-sm text-slate-400">Sin objetivos definidos.</p> : (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{project.objectives.map((o) => <li key={o}>{o}</li>)}</ul>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            {Object.entries(data.counts.by_type).map(([type, count]) => <Badge key={type} tone="blue">{label(TYPE_LABELS, type)}: {count}</Badge>)}
          </div>
        </section>

        <div className="grid gap-4 lg:grid-cols-2">
          <section className="card">
            <h2>Decisiones</h2>
            <ul className="mt-2 divide-y divide-slate-100">
              {data.decisions.map((m) => (
                <li key={m.id} className="py-2 text-sm">
                  <Link className="link" href={`/memories/detail?id=${m.id}`}>{m.title ?? m.content.slice(0, 90)}</Link>
                  {m.title && <p className="line-clamp-2 text-slate-600">{m.content}</p>}
                  <p className="text-xs text-slate-400">{formatDate(m.created_at)}</p>
                </li>
              ))}
            </ul>
            {data.decisions.length === 0 && <p className="text-sm text-slate-400">Sin decisiones registradas.</p>}
            <form onSubmit={addDecision} className="mt-3 space-y-2">
              <input className="input" placeholder="Título (opcional)" value={decisionTitle} onChange={(e) => setDecisionTitle(e.target.value)} aria-label="Título de la decisión" />
              <textarea className="input" placeholder="¿Qué se decidió y por qué?" value={decision} onChange={(e) => setDecision(e.target.value)} aria-label="Decisión" required />
              <button className="btn-secondary" disabled={busy || !decision.trim()}>Registrar decisión</button>
            </form>
          </section>

          <section className="card">
            <h2>Tareas</h2>
            {tasks.error && <Alert>{tasks.error}</Alert>}
            <ul className="mt-2 divide-y divide-slate-100">
              {tasks.data?.map((task) => {
                const done = task.status === "done";
                return (
                  <li key={task.id} className="flex items-center gap-2 py-2 text-sm">
                    <input type="checkbox" checked={done} disabled={busy} onChange={() => setTaskStatus(task, done ? "pending" : "done")} aria-label={`Completar ${task.title}`} />
                    <span className={`min-w-0 flex-1 ${done ? "text-slate-400 line-through" : ""}`}>{task.title}</span>
                    <Badge>{label(STATUS_LABELS, task.status)}</Badge>
                    <button className="text-xs text-red-600 hover:underline" disabled={busy} onClick={() => removeTask(task)}>Quitar</button>
                  </li>
                );
              })}
            </ul>
            {tasks.data?.length === 0 && <p className="text-sm text-slate-400">Sin tareas.</p>}
            <form onSubmit={addTask} className="mt-3 flex gap-2">
              <input className="input flex-1" placeholder="Nueva tarea pendiente" value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)} aria-label="Nueva tarea" required />
              <button className="btn-secondary" disabled={busy || !taskTitle.trim()}>Añadir</button>
            </form>
          </section>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <MemoryLinks title="Documentación" items={data.documents} empty="Sin documentos asociados." />
          <MemoryLinks title="Conversaciones" items={data.conversations} empty="Sin conversaciones asociadas." />
        </div>
        <MemoryLinks title="Recuerdos recientes" items={data.recent_memories} empty="Este proyecto aún no tiene recuerdos." />

        <section className="card">
          <h2>Relaciones con otros proyectos</h2>
          <ul className="mt-2 divide-y divide-slate-100">
            {data.relations.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                <Badge>{r.relation_type}</Badge>
                <span className="text-xs text-slate-400">{r.direction === "out" ? "→" : "←"}</span>
                <Link className="link" href={`/projects/detail?id=${r.project.id}`}>{r.project.name}</Link>
                <span className="min-w-0 flex-1 text-slate-600">{r.description}</span>
                <button className="text-xs text-red-600 hover:underline" disabled={busy} onClick={() => removeRelation(r.id)}>Quitar</button>
              </li>
            ))}
          </ul>
          {data.relations.length === 0 && <p className="text-sm text-slate-400">Sin relaciones.</p>}
          {others.length > 0 && (
            <form onSubmit={addRelation} className="mt-3 grid gap-2 sm:grid-cols-4">
              <select className="input" value={relatedId} onChange={(e) => setRelatedId(e.target.value)} aria-label="Proyecto relacionado" required>
                <option value="">Elegir proyecto…</option>
                {others.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <select className="input" value={relationType} onChange={(e) => setRelationType(e.target.value)} aria-label="Tipo de relación">
                {["related", "depends_on", "part_of", "continues", "uses"].map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <input className="input" placeholder="Descripción (opcional)" value={relationNote} onChange={(e) => setRelationNote(e.target.value)} aria-label="Descripción de la relación" />
              <button className="btn-secondary" disabled={busy || !relatedId}>Relacionar</button>
            </form>
          )}
        </section>

        <section className="card">
          <h2>Historial de cambios</h2>
          {history.error && <Alert>{history.error}</Alert>}
          <ul className="mt-2 divide-y divide-slate-100">
            {history.data?.items.map((entry) => (
              <li key={entry.id} className="flex flex-wrap items-baseline gap-x-3 py-2 text-sm">
                <span className="w-36 shrink-0 text-xs text-slate-400">{formatDate(entry.created_at)}</span>
                <span className="w-28 shrink-0 text-xs font-medium text-slate-500">{label(ACTION_LABELS, entry.action)}</span>
                <span className="min-w-0 flex-1">{entry.summary}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}

export default function ProjectDetailPage() {
  return (
    <Suspense fallback={<Loading />}>
      <Detail />
    </Suspense>
  );
}
