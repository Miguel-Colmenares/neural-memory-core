export const TYPE_LABELS: Record<string, string> = {
  episodic: "Episódica",
  semantic: "Semántica",
  project: "Proyecto",
  preference: "Preferencia",
  document: "Documental",
};

export const STATUS_LABELS: Record<string, string> = {
  active: "Activo",
  archived: "Archivado",
  paused: "En pausa",
  completed: "Completado",
  pending: "Pendiente",
  in_progress: "En curso",
  done: "Hecha",
  cancelled: "Cancelada",
};

export const SOURCE_LABELS: Record<string, string> = {
  manual: "Escrito a mano",
  conversation: "Conversación",
  document: "Documento",
  import: "Importación",
  api: "API",
  module: "Módulo",
};

export const ACTION_LABELS: Record<string, string> = {
  create: "Creación",
  update: "Actualización",
  correction: "Corrección",
  archive: "Archivado",
  restore: "Reactivación",
  revert: "Reversión",
  delete: "Eliminación",
  import: "Importación",
  export: "Exportación",
  backup: "Respaldo",
  backup_delete: "Respaldo eliminado",
  reindex: "Reindexación",
  password_change: "Cambio de contraseña",
  deactivate: "Desactivación",
};

export function label(map: Record<string, string>, key: string): string {
  return map[key] ?? key;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("es", { dateStyle: "medium", timeStyle: "short" });
}

export function formatDay(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("es", { dateStyle: "medium" });
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Ocurrió un error inesperado.";
}

export function splitTags(text: string): string[] {
  return text
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}
