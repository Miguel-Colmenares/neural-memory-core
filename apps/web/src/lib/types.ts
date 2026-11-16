export type Memory = {
  id: string;
  memory_type: string;
  kind: string;
  title: string | null;
  content: string;
  source_type: string;
  source_ref: string | null;
  provenance: Record<string, unknown>;
  project_id: string | null;
  project_name: string | null;
  module: string | null;
  tags: string[];
  importance: number;
  metadata: Record<string, unknown>;
  status: string;
  occurred_at: string | null;
  version: number;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

export type MemoryList = { items: Memory[]; total: number; limit: number; offset: number };

export type Ingestion = {
  outcome: "created" | "duplicate";
  memory: Memory;
  duplicate_of: string | null;
  relations: { memory_id: string; relation_type: string; confidence: number | null; origin: string }[];
  auto_tags: string[];
  warnings: string[];
  steps: { step: string; detail: string }[];
};

export type MemoryVersion = {
  version: number;
  change_type: string;
  change_reason: string | null;
  changed_fields: string[];
  changed_by: string | null;
  created_at: string;
  snapshot: Record<string, unknown>;
};

export type Relation = {
  id: string;
  source_id: string;
  target_id: string;
  relation_type: string;
  origin: string;
  confidence: number | null;
  note: string | null;
};

export type Neighbor = { relation: Relation; direction: string; memory: Memory };

export type Project = {
  id: string;
  slug: string;
  name: string;
  description: string;
  objectives: string[];
  status: string;
  created_at: string;
  updated_at: string;
  memory_count: number | null;
};

export type ProjectRelation = {
  id: string;
  relation_type: string;
  description: string;
  direction: string;
  project: Project;
};

export type ProjectOverview = {
  project: Project;
  counts: { active_memories: number; archived_memories: number; by_type: Record<string, number> };
  decisions: Memory[];
  documents: Memory[];
  conversations: Memory[];
  recent_memories: Memory[];
  relations: ProjectRelation[];
};

export type Task = {
  id: string;
  project_id: string | null;
  title: string;
  description: string;
  status: string;
  priority: number;
  due_date: string | null;
};

export type SearchResult = {
  memory: Memory;
  score: number;
  matched_by: string[];
  text_rank: number | null;
  semantic_similarity: number | null;
  excerpt: string;
  via_relation: { relation_type: string; origin: string; from_memory_id: string } | null;
  score_breakdown: Record<string, number>;
};

export type SearchResponse = {
  query: string;
  results: SearchResult[];
  total_candidates: number;
  warnings: string[];
  embedding: { provider: string; model: string; semantic: boolean };
};

export type Statement = { text: string; sources: number[] };

export type AnswerSource = {
  index: number;
  source_kind: string;
  id: string;
  label: string;
  excerpt: string;
  source_type?: string;
  source_ref?: string | null;
  created_at?: string;
  matched_by?: string[];
};

export type Answer = {
  question: string;
  answer: string;
  answer_mode: "extractive" | "llm";
  confirmed: Statement[];
  inferences: Statement[];
  not_found: string[];
  sources: AnswerSource[];
  interpretation: {
    intents: string[];
    projects: { id: string; name: string }[];
    search_terms: string[];
    filters: Record<string, unknown>;
  };
  warnings: string[];
};

export type ChangeEntry = {
  id: number;
  entity_type: string;
  entity_id: string;
  project_id: string | null;
  action: string;
  summary: string;
  details: Record<string, unknown>;
  actor: string | null;
  created_at: string;
};

export type IndexStatus = {
  memories_total: number;
  memories_indexed: number;
  memories_pending: number;
  vectors_total: number;
  vectors_from_other_provider: number;
};

export type Stats = {
  generated_at: string;
  memories: {
    total: number;
    by_status: Record<string, number>;
    by_type: Record<string, number>;
    by_source: Record<string, number>;
    created_last_7_days: number;
    last_created_at: string | null;
  };
  versions: number;
  relations: number;
  projects: { total: number; by_status: Record<string, number> };
  changes: { total: number; last_7_days: number; last_at: string | null };
  index: IndexStatus;
  modules: Record<string, Record<string, unknown>>;
};

export type GraphData = {
  nodes: { id: string; label: string; memory_type: string; kind: string; degree: number }[];
  edges: { id: string; source: string; target: string; relation_type: string; origin: string }[];
  total_relations: number;
};
