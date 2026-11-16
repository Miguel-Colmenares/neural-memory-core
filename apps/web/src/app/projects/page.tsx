"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Alert, Badge, Empty, Field, Loading, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { STATUS_LABELS, formatDay, label } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Project } from "@/lib/types";

export default function ProjectsPage() {
  const projects = useApi<Project[]>("/projects");
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [objectives, setObjectives] = useState("");
  const { busy, error, run } = useAction();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const ok = await run(async () => {
      await api("/projects", {
        method: "POST",
        body: { name, description, objectives: objectives.split("\n").map((o) => o.trim()).filter(Boolean) },
      });
    });
    if (ok) {
      setName("");
      setDescription("");
      setObjectives("");
      setShowForm(false);
      void projects.reload();
    }
  };

  return (
    <>
      <PageHeader
        title="Proyectos"
        subtitle="Cada proyecto tiene su propio espacio: objetivos, decisiones, documentos, conversaciones, tareas e historial."
        actions={<button className="btn-primary" onClick={() => setShowForm((v) => !v)}>{showForm ? "Cerrar formulario" : "Nuevo proyecto"}</button>}
      />
      {showForm && (
        <form onSubmit={submit} className="card mb-6 space-y-4">
          <h2>Nuevo proyecto</h2>
          {error && <Alert>{error}</Alert>}
          <Field label="Nombre"><input className="input" value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} /></Field>
          <Field label="Descripción"><textarea className="input min-h-20" value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
          <Field label="Objetivos" hint="Uno por línea."><textarea className="input min-h-20" value={objectives} onChange={(e) => setObjectives(e.target.value)} /></Field>
          <button className="btn-primary" disabled={busy || !name.trim()}>{busy ? "Creando…" : "Crear proyecto"}</button>
        </form>
      )}
      {projects.error && <Alert>{projects.error}</Alert>}
      {projects.loading && !projects.data && <Loading />}
      {projects.data && projects.data.length === 0 && <Empty>Todavía no hay proyectos.</Empty>}
      <div className="grid gap-4 md:grid-cols-2">
        {projects.data?.map((project) => (
          <Link key={project.id} href={`/projects/detail?id=${project.id}`} className="card transition hover:border-accent-500">
            <div className="flex items-center justify-between gap-2">
              <h2>{project.name}</h2>
              <Badge tone={project.status === "active" ? "green" : "slate"}>{label(STATUS_LABELS, project.status)}</Badge>
            </div>
            <p className="mt-1 line-clamp-2 text-sm text-slate-600">{project.description || "Sin descripción."}</p>
            <p className="mt-3 text-xs text-slate-400">
              {project.memory_count ?? 0} recuerdo(s) · creado el {formatDay(project.created_at)} · actividad {formatDay(project.updated_at)}
            </p>
          </Link>
        ))}
      </div>
    </>
  );
}
