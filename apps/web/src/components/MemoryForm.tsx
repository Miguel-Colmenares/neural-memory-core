"use client";

import { useState, type FormEvent } from "react";

import { Alert, Field } from "@/components/ui";
import { api } from "@/lib/api";
import { TYPE_LABELS, splitTags } from "@/lib/format";
import { useAction } from "@/lib/hooks";
import type { Ingestion, Project } from "@/lib/types";

export function MemoryForm({
  projects,
  defaultProjectId = "",
  onCreated,
}: {
  projects: Project[];
  defaultProjectId?: string;
  onCreated: () => void;
}) {
  const [content, setContent] = useState("");
  const [title, setTitle] = useState("");
  const [memoryType, setMemoryType] = useState("");
  const [kind, setKind] = useState("");
  const [projectId, setProjectId] = useState(defaultProjectId);
  const [tags, setTags] = useState("");
  const [importance, setImportance] = useState(3);
  const [sourceRef, setSourceRef] = useState("");
  const [result, setResult] = useState<Ingestion | null>(null);
  const { busy, error, run } = useAction();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const ok = await run(async () => {
      const created = await api<Ingestion>("/memories", {
        method: "POST",
        body: {
          content,
          title: title || null,
          memory_type: memoryType || null,
          kind: kind || null,
          project_id: projectId || null,
          tags: splitTags(tags),
          importance,
          source_ref: sourceRef || null,
        },
      });
      setResult(created);
    });
    if (ok) {
      setContent("");
      setTitle("");
      setTags("");
      setSourceRef("");
      onCreated();
    }
  };

  return (
    <form onSubmit={submit} className="card space-y-4">
      <h2>Nuevo recuerdo</h2>
      {error && <Alert>{error}</Alert>}
      {result && (
        <Alert kind={result.outcome === "created" ? "success" : "warning"}>
          {result.outcome === "created"
            ? `Recuerdo guardado como «${TYPE_LABELS[result.memory.memory_type] ?? result.memory.memory_type}».`
            : "Ya existía un recuerdo con el mismo contenido; no se duplicó."}
          {result.auto_tags.length > 0 && ` Etiquetas automáticas: ${result.auto_tags.join(", ")}.`}
          {result.relations.length > 0 && ` Relaciones detectadas: ${result.relations.length}.`}
          {result.warnings.map((warning) => <span key={warning} className="mt-1 block">{warning}</span>)}
        </Alert>
      )}
      <Field label="Contenido">
        <textarea className="input min-h-28" value={content} onChange={(e) => setContent(e.target.value)} required />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Título (opcional)"><input className="input" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} /></Field>
        <Field label="Tipo de memoria" hint="«Automático» lo decide por reglas y lo deja anotado.">
          <select className="input" value={memoryType} onChange={(e) => setMemoryType(e.target.value)}>
            <option value="">Automático</option>
            {Object.entries(TYPE_LABELS).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
          </select>
        </Field>
        <Field label="Clase (opcional)" hint="Por ejemplo: decision, idea, concept.">
          <input className="input" value={kind} onChange={(e) => setKind(e.target.value)} pattern="[a-zA-Z0-9_\-]*" maxLength={50} />
        </Field>
        <Field label="Proyecto">
          <select className="input" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            <option value="">Sin proyecto</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <Field label="Etiquetas" hint="Separadas por comas."><input className="input" value={tags} onChange={(e) => setTags(e.target.value)} /></Field>
        <Field label={`Importancia: ${importance}`}>
          <input type="range" min={1} max={5} value={importance} onChange={(e) => setImportance(Number(e.target.value))} className="w-full" />
        </Field>
        <Field label="Procedencia (opcional)" hint="De dónde sale: reunión, URL, libro…">
          <input className="input" value={sourceRef} onChange={(e) => setSourceRef(e.target.value)} maxLength={500} />
        </Field>
      </div>
      <button className="btn-primary" disabled={busy || !content.trim()}>{busy ? "Guardando…" : "Guardar recuerdo"}</button>
    </form>
  );
}
