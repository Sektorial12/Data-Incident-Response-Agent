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

export interface Assertion {
  urn: string;
  type: string;
  dataset: string;
  operator: string;
}

export interface AgentConfig {
  llm: Record<string, unknown>;
  lineage: Record<string, unknown>;
  confidence: Record<string, unknown>;
  timeout: Record<string, unknown>;
  agents: Record<string, unknown>;
  alert_routing: {
    rules: RoutingRule[];
    default_webhook_url: string;
    dedup_window_seconds: number;
  };
  env: {
    datahub_server_url: string;
    datahub_frontend_url: string;
    slack_webhook_configured: boolean;
    llm_provider: string;
  };
}

export interface RoutingRule {
  name: string;
  match: { platform?: string[]; min_confidence?: number };
  webhook_url: string;
}

export interface AgentStatus {
  status: "running" | "stopped";
  pid: number | null;
  uptime_seconds: number;
}

const API_BASE = import.meta.env.DEV ? "/api" : "http://localhost:8000";

async function fetchJSON<T>(path: string): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`);
  if (!resp.ok) throw new Error(`API error: ${resp.status}`);
  return resp.json();
}

async function postJSON<T>(path: string, body?: unknown): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) throw new Error(`API error: ${resp.status}`);
  return resp.json();
}

async function putJSON<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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

  // Management
  assertions: () => fetchJSON<{ assertions: Assertion[]; total: number }>("/manage/assertions"),
  createAssertion: (body: { assertion_id: string; dataset_urn: string; type?: string; operator?: string }) =>
    postJSON<{ status: string; assertion_urn: string }>("/manage/assertions", body),
  triggerFailure: (body: { assertion_urn: string; dataset_urn: string; error_message?: string; actual_value?: number }) =>
    postJSON<{ status: string; run_id: string }>("/manage/assertions/trigger", body),
  config: () => fetchJSON<AgentConfig>("/manage/config"),
  updateRouting: (body: { rules: RoutingRule[]; default_webhook_url: string; dedup_window_seconds: number }) =>
    putJSON<{ status: string; rules_count: number }>("/manage/config/routing", body),
  agentStatus: () => fetchJSON<AgentStatus>("/manage/agent/status"),
  agentRestart: () => postJSON<{ status: string; pid: number }>("/manage/agent/restart"),
  agentStop: () => postJSON<{ status: string }>("/manage/agent/stop"),
};
