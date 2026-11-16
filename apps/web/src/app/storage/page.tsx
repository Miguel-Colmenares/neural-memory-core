"use client";

import { useState } from "react";

import { Alert, Loading, PageHeader, Stat } from "@/components/ui";
import { api, download } from "@/lib/api";
import { formatBytes, formatDate } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";

type Storage = {
  database: { size_bytes: number; tables: { name: string; size_bytes: number; rows: number }[] };
  backups: { directory: string; count: number; total_bytes: number; items: { name: string; size_bytes: number; created_at: string }[] };
};

export default function StoragePage() {
  const storage = useApi<Storage>("/storage");
  const [backupLabel, setBackupLabel] = useState("");
  const { busy, error, notice, run } = useAction();

  const create = () =>
    run(async () => {
      const backup = await api<{ name: string }>(`/storage/backups?label=${encodeURIComponent(backupLabel)}`, { method: "POST" });
      setBackupLabel("");
      void storage.reload();
      return `Respaldo creado: ${backup.name}`;
    });
  const remove = (name: string) => {
    if (!window.confirm(`¿Eliminar el respaldo ${name}? No se puede deshacer.`)) return;
    void run(async () => {
      await api(`/storage/backups/${name}`, { method: "DELETE" });
      void storage.reload();
      return "Respaldo eliminado.";
    });
  };
  const get = (name: string) => run(async () => { await download(`/storage/backups/${name}`, name); });

  if (storage.loading && !storage.data) return <Loading />;
  if (storage.error || !storage.data) return <Alert>{storage.error ?? "Sin datos."}</Alert>;
  const { database, backups } = storage.data;

  return (
    <>
      <PageHeader title="Almacenamiento" subtitle="Tamaño real de la base de datos y copias de seguridad completas (pg_dump). Solo para administradores." />
      <div className="space-y-4">
        {error && <Alert>{error}</Alert>}
        {notice && <Alert kind="success">{notice}</Alert>}
        <div className="grid gap-4 sm:grid-cols-3">
          <Stat title="Base de datos" value={formatBytes(database.size_bytes)} />
          <Stat title="Respaldos" value={backups.count} hint={formatBytes(backups.total_bytes)} />
          <Stat title="Último respaldo" value={<span className="text-lg">{formatDate(backups.items[0]?.created_at)}</span>} />
        </div>
        <section className="card">
          <h2>Copias de seguridad</h2>
          <p className="mt-1 text-sm text-slate-500">
            Se guardan en <code className="rounded bg-slate-100 px-1 text-xs">{backups.directory}</code> en el servidor. Descárgalas y consérvalas fuera del servidor: contienen toda tu memoria y los usuarios. La restauración se hace con <code className="rounded bg-slate-100 px-1 text-xs">scripts/manage.py restore</code> (ver la guía de recuperación).
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <input className="input max-w-xs" placeholder="Etiqueta opcional" value={backupLabel} onChange={(e) => setBackupLabel(e.target.value)} maxLength={40} aria-label="Etiqueta del respaldo" />
            <button className="btn-primary" disabled={busy} onClick={create}>{busy ? "Trabajando…" : "Crear respaldo ahora"}</button>
          </div>
          {backups.items.length === 0 ? (
            <p className="mt-4 text-sm text-slate-400">Todavía no hay respaldos.</p>
          ) : (
            <table className="mt-4 w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-500"><tr><th className="py-2">Archivo</th><th>Tamaño</th><th>Creado</th><th /></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {backups.items.map((b) => (
                  <tr key={b.name}>
                    <td className="py-2 font-mono text-xs">{b.name}</td>
                    <td>{formatBytes(b.size_bytes)}</td>
                    <td>{formatDate(b.created_at)}</td>
                    <td className="space-x-3 text-right">
                      <button className="link text-xs" disabled={busy} onClick={() => get(b.name)}>Descargar</button>
                      <button className="text-xs text-red-600 hover:underline" disabled={busy} onClick={() => remove(b.name)}>Eliminar</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
        <section className="card">
          <h2>Tablas</h2>
          <table className="mt-3 w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-slate-500"><tr><th className="py-2">Tabla</th><th>Filas</th><th>Tamaño</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {database.tables.map((t) => (
                <tr key={t.name}><td className="py-2 font-mono text-xs">{t.name}</td><td>{t.rows.toLocaleString("es")}</td><td>{formatBytes(t.size_bytes)}</td></tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </>
  );
}
