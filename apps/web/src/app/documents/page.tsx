"use client";

import Link from "next/link";
import { useRef, useState, type FormEvent } from "react";

import { Alert, Empty, Field, Loading, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { formatBytes, formatDate, splitTags } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Ingestion, MemoryList, Project } from "@/lib/types";

export default function DocumentsPage() {
  const documents = useApi<MemoryList>("/documents?limit=100");
  const formats = useApi<{ extensions: string[]; note: string }>("/documents/formats");
  const projects = useApi<Project[]>("/projects");
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [projectId, setProjectId] = useState("");
  const [tags, setTags] = useState("");
  const { busy, error, notice, run } = useAction();

  const describe = (result: Ingestion) =>
    result.outcome === "duplicate"
      ? "Ese contenido ya estaba guardado; no se duplicó."
      : `Documento guardado (${result.memory.content.length.toLocaleString("es")} caracteres).`;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const ok = await run(async () => {
      if (file) {
        const form = new FormData();
        form.append("file", file);
        if (title) form.append("title", title);
        if (projectId) form.append("project_id", projectId);
        form.append("tags", tags);
        return describe(await api<Ingestion>("/documents/upload", { method: "POST", form }));
      }
      return describe(
        await api<Ingestion>("/documents", {
          method: "POST",
          body: { title, content: note, project_id: projectId || null, tags: splitTags(tags) },
        }),
      );
    });
    if (ok) {
      setFile(null);
      setTitle("");
      setNote("");
      setTags("");
      if (fileInput.current) fileInput.current.value = "";
      void documents.reload();
    }
  };

  const canSubmit = file !== null || (title.trim() !== "" && note.trim() !== "");

  return (
    <>
      <PageHeader title="Documentos" subtitle="Archivos, notas y material de referencia. Se guarda el texto extraído junto con el nombre, tamaño y huella del archivo original." />
      <form onSubmit={submit} className="card mb-6 space-y-4">
        <h2>Añadir documento</h2>
        {error && <Alert>{error}</Alert>}
        {notice && <Alert kind="success">{notice}</Alert>}
        <Field label="Archivo" hint={formats.data ? `Formatos: ${formats.data.extensions.join(" ")}. ${formats.data.note}` : undefined}>
          <input ref={fileInput} type="file" className="input" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </Field>
        {!file && (
          <Field label="…o escribe una nota">
            <textarea className="input min-h-24" value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
        )}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={file ? "Título (opcional)" : "Título"}><input className="input" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} /></Field>
          <Field label="Proyecto">
            <select className="input" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">Sin proyecto</option>
              {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
          <Field label="Etiquetas" hint="Separadas por comas."><input className="input" value={tags} onChange={(e) => setTags(e.target.value)} /></Field>
        </div>
        <button className="btn-primary" disabled={busy || !canSubmit}>{busy ? "Procesando…" : file ? "Subir archivo" : "Guardar nota"}</button>
      </form>

      {documents.error && <Alert>{documents.error}</Alert>}
      {documents.loading && !documents.data && <Loading />}
      {documents.data && documents.data.items.length === 0 && <Empty>No hay documentos todavía.</Empty>}
      {documents.data && documents.data.items.length > 0 && (
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="px-4 py-3">Documento</th><th className="px-4 py-3">Origen</th><th className="px-4 py-3">Proyecto</th><th className="px-4 py-3">Tamaño original</th><th className="px-4 py-3">Añadido</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {documents.data.items.map((doc) => (
                <tr key={doc.id}>
                  <td className="px-4 py-3"><Link className="link" href={`/memories/detail?id=${doc.id}`}>{doc.title ?? doc.content.slice(0, 60)}</Link></td>
                  <td className="px-4 py-3 text-slate-600">{doc.source_ref ?? "Nota"}</td>
                  <td className="px-4 py-3 text-slate-600">{doc.project_name ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{typeof doc.provenance.size_bytes === "number" ? formatBytes(doc.provenance.size_bytes) : "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{formatDate(doc.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
