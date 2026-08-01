# Data Incident Response Agent

An event-driven multi-agent system that listens for DataHub assertion failures, traces upstream lineage to identify root cause, validates hypotheses, and writes incident reports back to DataHub.

Built for the DataHub Hackathon.

## Problem

When a data quality assertion fails, data teams spend hours manually tracing lineage, checking upstream datasets, and identifying the root cause. Mean Time To Resolution (MTTR) for data incidents is typically measured in hours.

## Solution

An autonomous agent system that:
1. **Detects** assertion failures in real-time via DataHub Actions (event-driven)
2. **Traces** upstream lineage using `get_lineage` and `get_lineage_paths_between`
3. **Validates** candidate root causes by checking assertions, schema changes, and freshness
4. **Notifies** the team via Slack with actionable alerts
5. **Reports** incident findings back to DataHub as documents

MTTR: ~45 seconds vs ~4 hours manual.

## Architecture

```
DataHub Assertion Failure (Kafka Event)
    → DataHub Actions Plugin (event filter)
    → Coordinator Agent (orchestration)
        → Tracer Agent (lineage traversal, root cause identification)
        → Checker Agent (hypothesis validation)
        → Notifier Agent (Slack alert)
        → Reporter Agent (incident report → DataHub write-back)
```

## DataHub Capabilities Used

- DataHub Actions (event-driven automation)
- MCP Server (15+ tools, mutations enabled)
- DataHub Skills (lineage, quality, enrich)
- `get_lineage` (multi-hop UPSTREAM)
- `get_lineage_paths_between` (precise A-to-B path finding)
- `search` with SQL-like filters
- `get_entities`, `list_schema_fields`
- `save_document`, `add_tags`, `update_description` (write-back)
- `search_documents` (existing incident search)
- Service Accounts with Default Views

## Quick Start

```bash
# Clone
git clone https://github.com/Sektorial12/data-incident-response-agent.git
cd data-incident-response-agent

# Copy env
cp .env.example .env
# Edit .env with your credentials

# Install dependencies
pip install -r requirements.txt

# Run
python src/main.py
```

## Docker

```bash
docker-compose up -d
```

## Demo

1. DataHub running with healthcare dataset, assertions configured
2. Trigger: insert NULL into patient_id column
3. Agent detects assertion failure via DataHub Actions
4. Tracer agent traces 3-hop upstream lineage to find root cause
5. Checker agent validates hypothesis
6. Slack alert sent with root cause + lineage path
7. Incident report written to DataHub

## License

Apache 2.0
