import { useEffect, useState } from "react";
import {
  api,
  type Assertion,
  type AgentConfig,
  type AgentStatus,
  type RoutingRule,
} from "../lib/api";
import { usePoll } from "../hooks/usePoll";
import { Play, Plus, RefreshCw, Square, Zap, Save } from "lucide-react";

export function ManagePanel() {
  const [tab, setTab] = useState<"assertions" | "config" | "agent">("assertions");

  return (
    <div className="flex flex-col h-full">
      <div className="flex border-b border-border px-4 gap-1">
        <TabButton active={tab === "assertions"} onClick={() => setTab("assertions")}>
          Assertions
        </TabButton>
        <TabButton active={tab === "config"} onClick={() => setTab("config")}>
          Config & Routing
        </TabButton>
        <TabButton active={tab === "agent"} onClick={() => setTab("agent")}>
          Agent Control
        </TabButton>
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin p-4">
        {tab === "assertions" && <AssertionsTab />}
        {tab === "config" && <ConfigTab />}
        {tab === "agent" && <AgentTab />}
      </div>
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
        active ? "border-primary text-primary" : "border-transparent text-ink-tertiary hover:text-ink-secondary"
      }`}
    >
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Assertions tab
// ---------------------------------------------------------------------------

function AssertionsTab() {
  const { data, error, refetch } = usePoll(() => api.assertions(), 15000);
  const [showCreate, setShowCreate] = useState(false);
  const [triggerUrn, setTriggerUrn] = useState("");
  const [triggerDataset, setTriggerDataset] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const handleTrigger = async () => {
    if (!triggerUrn || !triggerDataset) return;
    setBusy(true);
    setMsg("");
    try {
      const res = await api.triggerFailure({ assertion_urn: triggerUrn, dataset_urn: triggerDataset });
      setMsg(`Emitted: ${res.run_id}`);
    } catch (e) {
      setMsg(`Error: ${e}`);
    }
    setBusy(false);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-ink-primary">DataHub Assertions</h3>
        <div className="flex gap-2">
          <button onClick={refetch} className="p-1.5 hover:bg-surface-hover rounded">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button onClick={() => setShowCreate(!showCreate)} className="flex items-center gap-1 px-2 py-1 text-xs bg-primary text-white rounded hover:bg-primary-hover">
            <Plus className="w-3 h-3" /> New
          </button>
        </div>
      </div>

      {showCreate && <CreateAssertionForm onDone={() => { setShowCreate(false); refetch(); }} />}

      {error && <div className="text-xs text-red">{error}</div>}

      <div className="space-y-1.5">
        {data?.assertions.map((a) => (
          <div key={a.urn} className="border border-border rounded p-3 text-xs bg-white">
            <div className="font-mono text-ink-primary break-all">{a.urn}</div>
            <div className="text-ink-tertiary mt-1">
              {a.type} &middot; {a.operator || "—"}
            </div>
            {a.dataset && <div className="text-ink-tertiary font-mono mt-0.5 break-all">{a.dataset}</div>}
            <button
              onClick={() => { setTriggerUrn(a.urn); setTriggerDataset(a.dataset); }}
              className="mt-2 flex items-center gap-1 px-2 py-1 text-2xs bg-amber-subtle text-amber border border-amber-border rounded hover:opacity-80"
            >
              <Zap className="w-3 h-3" /> Trigger Failure
            </button>
          </div>
        ))}
        {data && data.total === 0 && !error && (
          <div className="text-xs text-ink-tertiary py-4 text-center">No assertions found in DataHub</div>
        )}
      </div>

      {(triggerUrn || msg) && (
        <div className="border border-border rounded p-3 space-y-2 bg-white">
          <div className="text-xs font-semibold text-ink-primary">Trigger Test Failure</div>
          <input
            value={triggerUrn}
            onChange={(e) => setTriggerUrn(e.target.value)}
            placeholder="Assertion URN"
            className="w-full text-xs font-mono bg-white border border-border rounded px-2 py-1 text-ink-primary"
          />
          <input
            value={triggerDataset}
            onChange={(e) => setTriggerDataset(e.target.value)}
            placeholder="Dataset URN"
            className="w-full text-xs font-mono bg-white border border-border rounded px-2 py-1 text-ink-primary"
          />
          <div className="flex gap-2">
            <button
              onClick={handleTrigger}
              disabled={busy}
              className="flex items-center gap-1 px-3 py-1 text-xs bg-amber text-white rounded hover:opacity-90 disabled:opacity-50 border border-amber-border"
            >
              <Zap className="w-3 h-3" /> {busy ? "Sending..." : "Emit Failure"}
            </button>
            <button onClick={() => { setTriggerUrn(""); setTriggerDataset(""); setMsg(""); }} className="px-3 py-1 text-xs text-ink-tertiary">
              Cancel
            </button>
          </div>
          {msg && <div className="text-2xs text-ink-secondary">{msg}</div>}
        </div>
      )}
    </div>
  );
}

function CreateAssertionForm({ onDone }: { onDone: () => void }) {
  const [id, setId] = useState("");
  const [datasetUrn, setDatasetUrn] = useState("");
  const [op, setOp] = useState("EQUAL_TO");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const handleCreate = async () => {
    if (!id || !datasetUrn) return;
    setBusy(true);
    setErr("");
    try {
      await api.createAssertion({ assertion_id: id, dataset_urn: datasetUrn, operator: op });
      onDone();
    } catch (e) {
      setErr(String(e));
    }
    setBusy(false);
  };

  return (
    <div className="border border-border rounded p-3 space-y-2 mb-3 bg-white">
      <div className="text-xs font-semibold text-ink-primary">Create Assertion</div>
      <input value={id} onChange={(e) => setId(e.target.value)} placeholder="Assertion ID (e.g. billingPositive)" className="w-full text-xs bg-white border border-border rounded px-2 py-1 text-ink-primary" />
      <input value={datasetUrn} onChange={(e) => setDatasetUrn(e.target.value)} placeholder="Dataset URN" className="w-full text-xs font-mono bg-white border border-border rounded px-2 py-1 text-ink-primary" />
      <select value={op} onChange={(e) => setOp(e.target.value)} className="w-full text-xs bg-white border border-border rounded px-2 py-1 text-ink-primary">
        <option value="EQUAL_TO">EQUAL_TO</option>
        <option value="NOT_EQUAL_TO">NOT_EQUAL_TO</option>
        <option value="GREATER_THAN">GREATER_THAN</option>
        <option value="LESS_THAN">LESS_THAN</option>
      </select>
      <div className="flex gap-2">
        <button onClick={handleCreate} disabled={busy} className="px-3 py-1 text-xs bg-primary text-white rounded hover:bg-primary-hover disabled:opacity-50">
          {busy ? "Creating..." : "Create"}
        </button>
        <button onClick={onDone} className="px-3 py-1 text-xs text-ink-tertiary">Cancel</button>
      </div>
      {err && <div className="text-2xs text-red">{err}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Config tab
// ---------------------------------------------------------------------------

function ConfigTab() {
  const { data, error, refetch } = usePoll(() => api.config(), 10000);
  const [rules, setRules] = useState<RoutingRule[]>([]);
  const [defaultWebhook, setDefaultWebhook] = useState("");
  const [dedup, setDedup] = useState(900);
  const [dirty, setDirty] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  useEffect(() => {
    if (data) {
      setRules(data.alert_routing.rules || []);
      setDefaultWebhook(data.alert_routing.default_webhook_url || "");
      setDedup(data.alert_routing.dedup_window_seconds || 900);
      setDirty(false);
    }
  }, [data]);

  const save = async () => {
    setBusy(true);
    try {
      await api.updateRouting({ rules, default_webhook_url: defaultWebhook, dedup_window_seconds: dedup });
      setSaveMsg("Saved");
      setDirty(false);
      setTimeout(() => setSaveMsg(""), 2000);
    } catch (e) {
      setSaveMsg(`Error: ${e}`);
    }
    setBusy(false);
  };

  const [busy, setBusy] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-ink-primary">Configuration</h3>
        <div className="flex gap-2 items-center">
          {saveMsg && <span className="text-2xs text-ink-tertiary">{saveMsg}</span>}
          <button onClick={refetch} className="p-1.5 hover:bg-surface-hover rounded">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button onClick={save} disabled={!dirty || busy} className="flex items-center gap-1 px-2 py-1 text-xs bg-primary text-white rounded hover:bg-primary-hover disabled:opacity-50">
            <Save className="w-3 h-3" /> Save
          </button>
        </div>
      </div>

      {error && <div className="text-xs text-red">{error}</div>}

      {data && (
        <>
          <Section title="Environment">
            <KV label="DataHub Server" value={data.env.datahub_server_url || "not set"} />
            <KV label="DataHub Frontend" value={data.env.datahub_frontend_url || "not set"} />
            <KV label="LLM Provider" value={data.env.llm_provider} />
            <KV label="Slack Webhook" value={data.env.slack_webhook_configured ? "configured" : "not set"} />
          </Section>

          <Section title="Alert Routing">
            <div className="space-y-2">
              <label className="text-2xs text-ink-tertiary">Default Webhook URL</label>
              <input
                value={defaultWebhook}
                onChange={(e) => { setDefaultWebhook(e.target.value); setDirty(true); }}
                className="w-full text-xs font-mono bg-white border border-border rounded px-2 py-1 text-ink-primary"
              />
              <label className="text-2xs text-ink-tertiary">Dedup Window (seconds)</label>
              <input
                type="number"
                value={dedup}
                onChange={(e) => { setDedup(Number(e.target.value)); setDirty(true); }}
                className="w-24 text-xs bg-white border border-border rounded px-2 py-1 text-ink-primary"
              />
            </div>
          </Section>

          <Section title={`Routing Rules (${rules.length})`}>
            <div className="space-y-2">
              {rules.map((rule, i) => (
                <div key={i} className="border border-border rounded p-2 space-y-1 bg-white">
                  <input
                    value={rule.name}
                    onChange={(e) => { const r = [...rules]; r[i] = { ...r[i], name: e.target.value }; setRules(r); setDirty(true); }}
                    className="w-full text-xs bg-white border border-border rounded px-2 py-1 text-ink-primary"
                  />
                  <input
                    value={(rule.match.platform || []).join(", ")}
                    onChange={(e) => { const r = [...rules]; r[i] = { ...r[i], match: { ...r[i].match, platform: e.target.value.split(",").map(s => s.trim()).filter(Boolean) } }; setRules(r); setDirty(true); }}
                    placeholder="platforms (comma-separated)"
                    className="w-full text-xs bg-white border border-border rounded px-2 py-1 text-ink-primary"
                  />
                  <input
                    value={rule.webhook_url}
                    onChange={(e) => { const r = [...rules]; r[i] = { ...r[i], webhook_url: e.target.value }; setRules(r); setDirty(true); }}
                    placeholder="webhook URL or ${ENV_VAR}"
                    className="w-full text-xs font-mono bg-white border border-border rounded px-2 py-1 text-ink-primary"
                  />
                  <button
                    onClick={() => { setRules(rules.filter((_, j) => j !== i)); setDirty(true); }}
                    className="text-2xs text-red hover:underline"
                  >
                    Remove
                  </button>
                </div>
              ))}
              <button
                onClick={() => { setRules([...rules, { name: "New Rule", match: {}, webhook_url: "" }]); setDirty(true); }}
                className="flex items-center gap-1 text-xs text-primary hover:underline"
              >
                <Plus className="w-3 h-3" /> Add Rule
              </button>
            </div>
          </Section>
        </>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-border rounded p-3 bg-white">
      <div className="text-2xs text-primary uppercase tracking-wider mb-2 font-medium">{title}</div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-xs">
      <span className="text-ink-tertiary">{label}</span>
      <span className="font-mono text-ink-secondary">{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Agent tab
// ---------------------------------------------------------------------------

function AgentTab() {
  const { data, refetch } = usePoll(() => api.agentStatus(), 5000);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const restart = async () => {
    setBusy(true);
    try {
      const res = await api.agentRestart();
      setMsg(`Restarted (PID ${res.pid})`);
      refetch();
    } catch (e) {
      setMsg(`Error: ${e}`);
    }
    setBusy(false);
    setTimeout(() => setMsg(""), 3000);
  };

  const stop = async () => {
    setBusy(true);
    try {
      const res = await api.agentStop();
      setMsg(res.status);
      refetch();
    } catch (e) {
      setMsg(`Error: ${e}`);
    }
    setBusy(false);
    setTimeout(() => setMsg(""), 3000);
  };

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-ink-primary">Agent Lifecycle</h3>

      <div className="border border-border rounded p-3 bg-white">
        <div className="flex items-center gap-2 mb-2">
          <div className={`w-2 h-2 rounded-full ${data?.status === "running" ? "bg-green" : "bg-red"}`} />
          <span className="text-sm font-medium text-ink-primary">{data?.status || "..."}</span>
        </div>
        {data && (
          <div className="space-y-1">
            <KV label="PID" value={data.pid ? String(data.pid) : "—"} />
            <KV label="Uptime" value={data.uptime_seconds > 0 ? `${data.uptime_seconds.toFixed(0)}s` : "—"} />
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <button
          onClick={restart}
          disabled={busy}
          className="flex items-center gap-1 px-3 py-1.5 text-xs bg-primary text-white rounded hover:bg-primary-hover disabled:opacity-50"
        >
          <Play className="w-3 h-3" /> Restart
        </button>
        <button
          onClick={stop}
          disabled={busy || data?.status === "stopped"}
          className="flex items-center gap-1 px-3 py-1.5 text-xs bg-red text-white rounded hover:opacity-90 disabled:opacity-50"
        >
          <Square className="w-3 h-3" /> Stop
        </button>
      </div>

      {msg && <div className="text-xs text-ink-secondary">{msg}</div>}
    </div>
  );
}
