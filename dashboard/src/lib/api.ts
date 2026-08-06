export interface Incident {
  id: string;
  assertion_urn: string;
  dataset_urn: string;
  status: "active" | "resolved";
  error_message: string | null;
  root_causes: RootCause[] | null;
  agent_results: AgentResults | null;
  elapsed_seconds: number | null;
  created_at: string;
  resolved_at: string | null;
  dedup_key: string | null;
}

export interface RootCause {
  candidate_urn?: string;
  urn?: string;
  confidence: number;
  reasoning?: string;
  reason?: string;
}

export interface AgentResults {
  tracer?: AgentResult;
  checker?: AgentResult;
  notifier?: AgentResult;
  reporter?: AgentResult;
}

export interface AgentResult {
  status: string;
  result?: Record<string, unknown>;
  error?: string;
}

export interface Stats {
  total: number;
  active: number;
  resolved: number;
  avg_mttr_seconds: number;
}

export interface Health {
  status: string;
  uptime_seconds: number;
}

const API_BASE = import.meta.env.DEV ? "/api" : "http://localhost:8000";

async function fetchJSON<T>(path: string): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`);
  if (!resp.ok) throw new Error(`API error: ${resp.status}`);
  return resp.json();
}

export const api = {
  health: () => fetchJSON<Health>("/health"),
  stats: () => fetchJSON<Stats>("/stats"),
  incidents: (status?: string, limit = 50) =>
    fetchJSON<Incident[]>(
      `/incidents?limit=${limit}${status ? `&status=${status}` : ""}`
    ),
  incident: (id: string) => fetchJSON<Incident | null>(`/incidents/${id}`),
};
