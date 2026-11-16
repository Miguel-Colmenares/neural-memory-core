"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { Alert, Empty, Field, Loading, PageHeader } from "@/components/ui";
import { query } from "@/lib/api";
import { TYPE_LABELS, label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { GraphData, Project } from "@/lib/types";

const WIDTH = 960;
const HEIGHT = 620;
const COLORS: Record<string, string> = {
  episodic: "#f59e0b",
  semantic: "#5b7cfa",
  project: "#10b981",
  preference: "#ec4899",
  document: "#64748b",
};

type Point = { x: number; y: number };

/** Disposición por fuerzas, determinista (sin azar) para que el grafo no cambie al recargar. */
function layout(graph: GraphData): Map<string, Point> {
  const nodes = graph.nodes;
  const positions = new Map<string, Point>();
  nodes.forEach((node, index) => {
    const angle = (2 * Math.PI * index) / Math.max(nodes.length, 1);
    const radius = 180 + (index % 5) * 22;
    positions.set(node.id, { x: WIDTH / 2 + radius * Math.cos(angle), y: HEIGHT / 2 + radius * Math.sin(angle) });
  });
  const ideal = Math.sqrt((WIDTH * HEIGHT) / Math.max(nodes.length, 1)) * 0.6;
  for (let step = 0; step < 220; step += 1) {
    const cooling = 1 - step / 220;
    const moves = new Map<string, Point>(nodes.map((n) => [n.id, { x: 0, y: 0 }]));
    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const a = positions.get(nodes[i].id)!;
        const b = positions.get(nodes[j].id)!;
        const dx = a.x - b.x || 0.01;
        const dy = a.y - b.y || 0.01;
        const distance = Math.max(Math.hypot(dx, dy), 1);
        const force = (ideal * ideal) / distance;
        const ma = moves.get(nodes[i].id)!;
        const mb = moves.get(nodes[j].id)!;
        ma.x += (dx / distance) * force;
        ma.y += (dy / distance) * force;
        mb.x -= (dx / distance) * force;
        mb.y -= (dy / distance) * force;
      }
    }
    for (const edge of graph.edges) {
      const a = positions.get(edge.source);
      const b = positions.get(edge.target);
      if (!a || !b) continue;
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const distance = Math.max(Math.hypot(dx, dy), 1);
      const force = (distance * distance) / ideal;
      const ma = moves.get(edge.source)!;
      const mb = moves.get(edge.target)!;
      ma.x -= (dx / distance) * force;
      ma.y -= (dy / distance) * force;
      mb.x += (dx / distance) * force;
      mb.y += (dy / distance) * force;
    }
    for (const node of nodes) {
      const position = positions.get(node.id)!;
      const move = moves.get(node.id)!;
      const length = Math.max(Math.hypot(move.x, move.y), 1);
      const limit = Math.min(length, 40 * cooling + 1);
      position.x = Math.min(WIDTH - 40, Math.max(40, position.x + (move.x / length) * limit));
      position.y = Math.min(HEIGHT - 30, Math.max(30, position.y + (move.y / length) * limit));
    }
  }
  return positions;
}

export default function GraphPage() {
  const router = useRouter();
  const projects = useApi<Project[]>("/projects");
  const [projectId, setProjectId] = useState("");
  const [memoryType, setMemoryType] = useState("");
  const [focusId, setFocusId] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const graph = useApi<GraphData>(`/graph${query({ project_id: projectId, memory_type: memoryType, focus_id: focusId, limit: 120 })}`);
  const positions = useMemo(() => (graph.data ? layout(graph.data) : new Map<string, Point>()), [graph.data]);
  const selectedNode = graph.data?.nodes.find((n) => n.id === selected);
  const selectedEdges = graph.data?.edges.filter((e) => e.source === selected || e.target === selected) ?? [];

  return (
    <>
      <PageHeader title="Relaciones entre conocimientos" subtitle="Cada punto es un recuerdo y cada línea una relación. Las líneas discontinuas fueron detectadas automáticamente; las continuas las creaste tú." />
      <div className="card mb-4 grid gap-3 sm:grid-cols-3">
        <Field label="Proyecto">
          <select className="input" value={projectId} onChange={(e) => { setProjectId(e.target.value); setFocusId(""); }}>
            <option value="">Todos</option>
            {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <Field label="Tipo de memoria">
          <select className="input" value={memoryType} onChange={(e) => { setMemoryType(e.target.value); setFocusId(""); }}>
            <option value="">Todos</option>
            {Object.entries(TYPE_LABELS).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
          </select>
        </Field>
        <div className="flex items-end">
          {focusId && <button className="btn-secondary" onClick={() => setFocusId("")}>Ver todo el grafo</button>}
        </div>
      </div>
      {graph.error && <Alert>{graph.error}</Alert>}
      {graph.loading && !graph.data && <Loading />}
      {graph.data && graph.data.nodes.length === 0 && (
        <Empty>Aún no hay relaciones que mostrar ({graph.data.total_relations} en total). Se crean al incorporar recuerdos parecidos o manualmente desde un recuerdo.</Empty>
      )}
      {graph.data && graph.data.nodes.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
          <div className="card overflow-hidden p-0">
            <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-auto w-full" role="img" aria-label="Grafo de relaciones entre recuerdos">
              {graph.data.edges.map((edge) => {
                const a = positions.get(edge.source);
                const b = positions.get(edge.target);
                if (!a || !b) return null;
                const active = selected !== null && (edge.source === selected || edge.target === selected);
                return (
                  <line key={edge.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                    stroke={edge.relation_type === "contradicts" ? "#ef4444" : active ? "#4563e6" : "#cbd5e1"}
                    strokeWidth={active ? 2 : 1.2} strokeDasharray={edge.origin === "auto" ? "5 4" : undefined}>
                    <title>{edge.relation_type} ({edge.origin})</title>
                  </line>
                );
              })}
              {graph.data.nodes.map((node) => {
                const p = positions.get(node.id);
                if (!p) return null;
                return (
                  <g key={node.id} transform={`translate(${p.x},${p.y})`} className="cursor-pointer" onClick={() => setSelected(node.id)}>
                    <circle r={7 + Math.min(node.degree, 8)} fill={COLORS[node.memory_type] ?? "#94a3b8"} stroke={selected === node.id ? "#0b1020" : "#ffffff"} strokeWidth={2} />
                    <text y={-12 - Math.min(node.degree, 8)} textAnchor="middle" fontSize={11} fill="#334155">{node.label.length > 28 ? `${node.label.slice(0, 28)}…` : node.label}</text>
                    <title>{node.label}</title>
                  </g>
                );
              })}
            </svg>
            <div className="flex flex-wrap gap-3 border-t border-slate-100 px-4 py-2 text-xs text-slate-500">
              {Object.entries(COLORS).map(([type, color]) => (
                <span key={type} className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color }} />{label(TYPE_LABELS, type)}</span>
              ))}
              <span className="ml-auto">{graph.data.nodes.length} recuerdos · {graph.data.edges.length} relaciones mostradas de {graph.data.total_relations}</span>
            </div>
          </div>
          <aside className="card text-sm">
            {selectedNode ? (
              <>
                <h2>{selectedNode.label}</h2>
                <p className="mt-1 text-xs text-slate-500">{label(TYPE_LABELS, selectedNode.memory_type)} · {selectedNode.kind} · {selectedNode.degree} relación(es)</p>
                <ul className="mt-3 space-y-1">
                  {selectedEdges.map((edge) => {
                    const otherId = edge.source === selected ? edge.target : edge.source;
                    const other = graph.data?.nodes.find((n) => n.id === otherId);
                    return (
                      <li key={edge.id}>
                        <span className="text-xs text-slate-400">{edge.relation_type}</span>{" "}
                        <button className="link text-left" onClick={() => setSelected(otherId)}>{other?.label ?? otherId}</button>
                      </li>
                    );
                  })}
                </ul>
                <div className="mt-4 flex flex-col gap-2">
                  <button className="btn-primary" onClick={() => router.push(`/memories/detail?id=${selectedNode.id}`)}>Abrir recuerdo</button>
                  <button className="btn-secondary" onClick={() => setFocusId(selectedNode.id)}>Centrar el grafo aquí</button>
                </div>
              </>
            ) : (
              <p className="text-slate-500">Selecciona un punto para ver sus relaciones.</p>
            )}
          </aside>
        </div>
      )}
    </>
  );
}
