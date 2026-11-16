"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Alert, Badge, Empty, Field, Highlight, MemoryCard, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { TYPE_LABELS, formatDate } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Answer, AnswerSource, Project, SearchResponse, Statement } from "@/lib/types";

const MATCH_LABELS: Record<string, string> = {
  text: "Texto",
  semantic: "Similitud",
  relation: "Relación",
  filter: "Filtro",
};

function sourceHref(source: AnswerSource): string | null {
  if (source.source_kind === "memory") return `/memories/detail?id=${source.id}`;
  if (source.source_kind === "project") return `/projects/detail?id=${source.id}`;
  return null;
}

function Statements({ title, tone, items }: { title: string; tone: string; items: Statement[] }) {
  if (items.length === 0) return null;
  return (
    <section className={`rounded-xl border p-4 ${tone}`}>
      <h2>{title}</h2>
      <ul className="mt-2 space-y-2 text-sm">
        {items.map((item, index) => (
          <li key={index}>
            {item.text}{" "}
            {item.sources.map((source) => (
              <a key={source} href={`#fuente-${source}`} className="link text-xs">[{source}]</a>
            ))}
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function SearchPage() {
  const projects = useApi<Project[]>("/projects");
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"ask" | "search">("ask");
  const [searchMode, setSearchMode] = useState("hybrid");
  const [memoryType, setMemoryType] = useState("");
  const [projectId, setProjectId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [results, setResults] = useState<SearchResponse | null>(null);
  const { busy, error, run } = useAction();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) return;
    const filters = {
      memory_types: memoryType ? [memoryType] : [],
      project_ids: projectId ? [projectId] : [],
      status: includeArchived ? "any" : "active",
      date_from: dateFrom ? new Date(dateFrom).toISOString() : null,
      date_to: dateTo ? new Date(`${dateTo}T23:59:59`).toISOString() : null,
    };
    await run(async () => {
      if (mode === "ask") {
        setResults(null);
        setAnswer(await api<Answer>("/ask", { method: "POST", body: { question: text, filters } }));
      } else {
        setAnswer(null);
        setResults(
          await api<SearchResponse>("/search", {
            method: "POST",
            body: { query: text, mode: searchMode, limit: 20, filters },
          }),
        );
      }
    });
  };

  return (
    <>
      <PageHeader
        title="Buscador inteligente"
        subtitle="Pregunta en lenguaje natural o busca recuerdos. Las respuestas solo usan lo que está guardado y siempre citan sus fuentes."
      />
      <form onSubmit={submit} className="card space-y-4">
        <div className="flex gap-2">
          <input
            className="input flex-1"
            placeholder={mode === "ask" ? "¿Qué decisiones había tomado en mi último proyecto?" : "Palabras o tema a buscar"}
            value={text}
            onChange={(e) => setText(e.target.value)}
            aria-label="Consulta"
          />
          <button className="btn-primary" disabled={busy || !text.trim()}>
            {busy ? "Buscando…" : mode === "ask" ? "Preguntar" : "Buscar"}
          </button>
        </div>
        <div className="flex flex-wrap gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input type="radio" checked={mode === "ask"} onChange={() => setMode("ask")} /> Responder con fuentes
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" checked={mode === "search"} onChange={() => setMode("search")} /> Listar recuerdos
          </label>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Field label="Tipo de memoria">
            <select className="input" value={memoryType} onChange={(e) => setMemoryType(e.target.value)}>
              <option value="">Todos</option>
              {Object.entries(TYPE_LABELS).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
            </select>
          </Field>
          <Field label="Proyecto">
            <select className="input" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
              <option value="">Todos</option>
              {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
          <Field label="Desde"><input type="date" className="input" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></Field>
          <Field label="Hasta"><input type="date" className="input" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></Field>
          {mode === "search" && (
            <Field label="Método">
              <select className="input" value={searchMode} onChange={(e) => setSearchMode(e.target.value)}>
                <option value="hybrid">Híbrido</option>
                <option value="text">Solo texto</option>
                <option value="semantic">Solo embeddings</option>
              </select>
            </Field>
          )}
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={includeArchived} onChange={(e) => setIncludeArchived(e.target.checked)} /> Incluir archivados
        </label>
      </form>

      <div className="mt-6 space-y-4">
        {error && <Alert>{error}</Alert>}

        {answer && (
          <>
            {answer.warnings.map((warning) => <Alert key={warning} kind="warning">{warning}</Alert>)}
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <Badge tone={answer.answer_mode === "llm" ? "violet" : "slate"}>
                {answer.answer_mode === "llm" ? "Redactada por el modelo de lenguaje" : "Respuesta extractiva (citas literales)"}
              </Badge>
              {answer.interpretation.projects.map((p) => <Badge key={p.id} tone="blue">Proyecto: {p.name}</Badge>)}
              {answer.interpretation.intents.map((intent) => <Badge key={intent}>{intent}</Badge>)}
              {answer.interpretation.search_terms.length > 0 && <span>Términos: {answer.interpretation.search_terms.join(", ")}</span>}
            </div>
            {answer.answer_mode === "llm" && (
              <section className="card whitespace-pre-line text-sm">{answer.answer}</section>
            )}
            <Statements title="Confirmado por tus recuerdos" tone="border-emerald-200 bg-emerald-50" items={answer.confirmed} />
            <Statements title="Inferencias del sistema" tone="border-amber-200 bg-amber-50" items={answer.inferences} />
            {answer.not_found.length > 0 && (
              <section className="rounded-xl border border-slate-300 bg-slate-100 p-4">
                <h2>No encontrado</h2>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
                  {answer.not_found.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </section>
            )}
            {answer.sources.length > 0 && (
              <section className="card">
                <h2>Fuentes utilizadas</h2>
                <ol className="mt-3 space-y-3">
                  {answer.sources.map((source) => {
                    const href = sourceHref(source);
                    return (
                      <li key={source.index} id={`fuente-${source.index}`} className="text-sm">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold text-slate-900">[{source.index}]</span>
                          <Badge>{source.source_kind}</Badge>
                          {href ? <Link href={href} className="link">{source.label}</Link> : <span className="font-medium">{source.label}</span>}
                          {source.created_at && <span className="text-xs text-slate-400">{formatDate(source.created_at)}</span>}
                          {source.source_ref && <span className="text-xs text-slate-400">Procedencia: {source.source_ref}</span>}
                        </div>
                        {source.excerpt && <p className="mt-1 text-slate-600">{source.excerpt}</p>}
                      </li>
                    );
                  })}
                </ol>
              </section>
            )}
          </>
        )}

        {results && (
          <>
            {results.warnings.map((warning) => <Alert key={warning} kind="warning">{warning}</Alert>)}
            <p className="text-xs text-slate-500">
              {results.results.length} resultado(s) de {results.total_candidates} candidato(s) · embeddings: {results.embedding.provider}
              {!results.embedding.semantic && " (parecido léxico; no entiende sinónimos)"}
            </p>
            {results.results.length === 0 && <Empty>No hay recuerdos que coincidan con esa búsqueda.</Empty>}
            {results.results.map((result) => (
              <div key={result.memory.id}>
                <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span className="font-semibold text-slate-700">Puntuación {result.score.toFixed(2)}</span>
                  {result.matched_by.map((m) => <Badge key={m} tone="green">{MATCH_LABELS[m] ?? m}</Badge>)}
                  {result.semantic_similarity !== null && <span>similitud {result.semantic_similarity.toFixed(2)}</span>}
                  {result.via_relation && <span>vía relación «{result.via_relation.relation_type}» ({result.via_relation.origin})</span>}
                </div>
                <MemoryCard memory={result.memory} excerpt={<Highlight text={result.excerpt} />} />
              </div>
            ))}
          </>
        )}
      </div>
    </>
  );
}
