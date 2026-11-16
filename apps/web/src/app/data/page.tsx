"use client";

import { useRef, useState } from "react";

import { Alert, PageHeader } from "@/components/ui";
import { api, download } from "@/lib/api";
import { useAction } from "@/lib/hooks";

type ImportReport = {
  sections: Record<string, { imported: number; skipped: number }>;
  modules: Record<string, Record<string, number | string>>;
  reindex: { processed: number; failed: number };
};

const SECTION_LABELS: Record<string, string> = {
  projects: "Proyectos",
  project_relations: "Relaciones entre proyectos",
  memories: "Recuerdos",
  memory_versions: "Versiones",
  memory_relations: "Relaciones entre recuerdos",
  change_log: "Entradas de historial",
};

export default function DataPage() {
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const exporting = useAction();
  const importing = useAction();

  const exportAll = () =>
    exporting.run(async () => {
      await download("/data/export", "nmc-export.json");
      return "Exportación descargada. Guárdala en un lugar seguro: contiene toda tu memoria.";
    });

  const importFile = async () => {
    if (!file) return;
    const ok = await importing.run(async () => {
      const form = new FormData();
      form.append("file", file);
      setReport(await api<ImportReport>("/data/import", { method: "POST", form }));
      return "Importación completada.";
    });
    if (ok) {
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  return (
    <>
      <PageHeader title="Exportar e importar" subtitle="Tu memoria es tuya: llévatela completa en un archivo JSON legible y recupérala en cualquier instalación. Solo para administradores." />
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="card space-y-3">
          <h2>Exportar toda la memoria</h2>
          <p className="text-sm text-slate-600">
            Incluye proyectos, recuerdos, todas sus versiones, relaciones, historial y datos de los módulos. No incluye usuarios ni contraseñas, ni embeddings (se regeneran al importar).
          </p>
          {exporting.error && <Alert>{exporting.error}</Alert>}
          {exporting.notice && <Alert kind="success">{exporting.notice}</Alert>}
          <button className="btn-primary" disabled={exporting.busy} onClick={exportAll}>{exporting.busy ? "Preparando…" : "Descargar exportación JSON"}</button>
        </section>
        <section className="card space-y-3">
          <h2>Importar una exportación</h2>
          <p className="text-sm text-slate-600">
            La importación fusiona: añade lo que falta y nunca sobrescribe un recuerdo que ya existe. Al terminar se regeneran los índices de búsqueda.
          </p>
          {importing.error && <Alert>{importing.error}</Alert>}
          {importing.notice && <Alert kind="success">{importing.notice}</Alert>}
          <input ref={fileInput} type="file" accept="application/json,.json" className="input" onChange={(e) => setFile(e.target.files?.[0] ?? null)} aria-label="Archivo de exportación" />
          <button className="btn-primary" disabled={importing.busy || !file} onClick={importFile}>{importing.busy ? "Importando…" : "Importar archivo"}</button>
          {report && (
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-500"><tr><th className="py-2">Sección</th><th>Importados</th><th>Ya existían</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {Object.entries(report.sections).map(([section, counts]) => (
                  <tr key={section}><td className="py-2">{SECTION_LABELS[section] ?? section}</td><td>{counts.imported}</td><td>{counts.skipped}</td></tr>
                ))}
                {Object.entries(report.modules).map(([name, counts]) => (
                  <tr key={name}><td className="py-2">Módulo {name}</td><td>{counts.imported ?? "—"}</td><td>{counts.skipped ?? counts.error ?? "—"}</td></tr>
                ))}
                <tr><td className="py-2">Recuerdos reindexados</td><td>{report.reindex.processed}</td><td>{report.reindex.failed} con error</td></tr>
              </tbody>
            </table>
          )}
        </section>
      </div>
    </>
  );
}
