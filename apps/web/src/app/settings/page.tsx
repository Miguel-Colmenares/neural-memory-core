"use client";

import { useState } from "react";

import { Alert, Badge, Loading, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { IndexStatus } from "@/lib/types";

type Providers = {
  embeddings: {
    provider: string;
    model: string;
    dimensions: number;
    semantic: boolean;
    external: boolean;
    api_base: string | null;
    api_key_configured: boolean;
    may_incur_cost: boolean;
    index: IndexStatus;
    available_providers: { id: string; description: string; cost: string }[];
  };
  llm: {
    enabled: boolean;
    provider: string;
    model: string | null;
    api_base: string | null;
    api_key_configured: boolean;
    may_incur_cost: boolean;
    answer_mode: string;
  };
  configured_via: string;
};
type TestResult = Record<string, { ok: boolean | null; error?: string; detail?: string; milliseconds?: number; dimensions?: number }>;
type SystemInfo = { version: string; environment: string; modules: { name: string; version: string; description: string; kinds: string[] }[] };

function Row({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-slate-100 py-2 text-sm last:border-0">
      <dt className="text-slate-500">{name}</dt>
      <dd className="text-right font-medium text-slate-900">{children}</dd>
    </div>
  );
}

export default function SettingsPage() {
  const providers = useApi<Providers>("/system/providers");
  const info = useApi<SystemInfo>("/system/info");
  const [test, setTest] = useState<TestResult | null>(null);
  const { busy, error, notice, run } = useAction();

  const runTest = () =>
    run(async () => {
      setTest(await api<TestResult>("/system/providers/test", { method: "POST" }));
    });
  const reindex = (all: boolean) =>
    run(async () => {
      const report = await api<{ processed: number; failed: number }>(`/system/reindex?all=${all}`, { method: "POST" });
      void providers.reload();
      return `Reindexación terminada: ${report.processed} recuerdo(s) procesados, ${report.failed} con error.`;
    });

  if (providers.loading && !providers.data) return <Loading />;
  if (providers.error || !providers.data) return <Alert>{providers.error ?? "Sin datos."}</Alert>;
  const { embeddings, llm } = providers.data;

  return (
    <>
      <PageHeader
        title="Proveedores de IA"
        subtitle="Estado real de la configuración. Las claves nunca se muestran ni se guardan en la base de datos: se definen con variables de entorno en el archivo .env del servidor."
        actions={<button className="btn-secondary" disabled={busy} onClick={runTest}>Probar conexión</button>}
      />
      <div className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {notice && <Alert kind="success">{notice}</Alert>}
        {test && (
          <Alert kind={test.embeddings?.ok && test.llm?.ok !== false ? "success" : "warning"}>
            Embeddings: {test.embeddings?.ok ? `correcto (${test.embeddings.dimensions} dimensiones, ${test.embeddings.milliseconds} ms)` : `error: ${test.embeddings?.error}`}.{" "}
            Modelo de lenguaje: {test.llm?.ok === null ? test.llm.detail : test.llm?.ok ? `correcto (${test.llm.milliseconds} ms)` : `error: ${test.llm?.error}`}
          </Alert>
        )}
        <div className="grid gap-4 lg:grid-cols-2">
          <section className="card">
            <div className="flex items-center justify-between">
              <h2>Embeddings (búsqueda por similitud)</h2>
              <Badge tone={embeddings.may_incur_cost ? "amber" : "green"}>{embeddings.may_incur_cost ? "Puede tener costo" : "Gratis y local"}</Badge>
            </div>
            <dl className="mt-3">
              <Row name="Proveedor activo">{embeddings.provider}</Row>
              <Row name="Modelo">{embeddings.model}</Row>
              <Row name="Dimensiones">{embeddings.dimensions}</Row>
              <Row name="Entiende significado">{embeddings.semantic ? "Sí" : "No (solo parecido léxico)"}</Row>
              <Row name="Envía texto a un servicio externo">{embeddings.external ? `Sí (${embeddings.api_base})` : "No"}</Row>
              <Row name="Clave de API">{embeddings.api_key_configured ? "Configurada" : "No configurada"}</Row>
              <Row name="Recuerdos indexados">{embeddings.index.memories_indexed} de {embeddings.index.memories_total}</Row>
              <Row name="Vectores de otro proveedor">{embeddings.index.vectors_from_other_provider}</Row>
            </dl>
            {!embeddings.semantic && (
              <div className="mt-3"><Alert kind="info">El proveedor «hashing» encuentra textos con palabras parecidas, pero no sinónimos ni paráfrasis. Para búsqueda por significado activa «fastembed» (gratis, local) en el archivo .env y reindexa.</Alert></div>
            )}
            <div className="mt-4 flex flex-wrap gap-2">
              <button className="btn-secondary" disabled={busy} onClick={() => reindex(false)}>Indexar pendientes ({embeddings.index.memories_pending})</button>
              <button className="btn-secondary" disabled={busy} onClick={() => { if (window.confirm("Se regenerarán los embeddings de todos los recuerdos. ¿Continuar?")) void reindex(true); }}>Reindexar todo</button>
            </div>
            <h3 className="mt-5 text-xs font-semibold uppercase tracking-wide text-slate-500">Proveedores disponibles</h3>
            <ul className="mt-2 space-y-2 text-sm">
              {embeddings.available_providers.map((p) => (
                <li key={p.id}><code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{p.id}</code> {p.description} <span className="text-xs text-slate-400">({p.cost})</span></li>
              ))}
            </ul>
          </section>
          <section className="card">
            <div className="flex items-center justify-between">
              <h2>Modelo de lenguaje (redacción de respuestas)</h2>
              <Badge tone={llm.enabled ? "amber" : "slate"}>{llm.enabled ? "Activo: puede tener costo" : "Desactivado"}</Badge>
            </div>
            <dl className="mt-3">
              <Row name="Modo de respuesta">{llm.answer_mode === "llm" ? "Redactada por el modelo, con fuentes verificadas" : "Extractiva (citas literales)"}</Row>
              <Row name="Proveedor">{llm.provider}</Row>
              <Row name="Modelo">{llm.model ?? "—"}</Row>
              <Row name="Servidor">{llm.api_base ?? "—"}</Row>
              <Row name="Clave de API">{llm.api_key_configured ? "Configurada" : "No configurada"}</Row>
            </dl>
            <p className="mt-3 text-sm text-slate-500">
              Es opcional. Sin modelo, el buscador responde citando literalmente tus recuerdos. Con modelo, este solo puede usar las fuentes recuperadas y se descarta cualquier afirmación sin fuente.
            </p>
            <p className="mt-3 text-xs text-slate-400">Configuración: {providers.data.configured_via}.</p>
          </section>
        </div>
        <section className="card">
          <h2>Módulos activos</h2>
          {info.error && <Alert>{info.error}</Alert>}
          {info.data && (
            <>
              <p className="mt-1 text-xs text-slate-500">Neural Memory Core {info.data.version} · entorno {info.data.environment}</p>
              <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {info.data.modules.map((m) => (
                  <li key={m.name} className="rounded-lg border border-slate-200 p-3 text-sm">
                    <p className="font-medium text-slate-900">{m.name} <span className="text-xs font-normal text-slate-400">v{m.version}</span></p>
                    <p className="mt-1 text-slate-600">{m.description}</p>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </div>
    </>
  );
}
