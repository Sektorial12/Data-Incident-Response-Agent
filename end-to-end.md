# End-to-End Verification Guide

Full walkthrough of the Data Incident Response Agent — from infrastructure setup to triggering an assertion failure and observing the automated incident response via the dashboard UI.

---

## Prerequisites

### 1. Infrastructure

- **DataHub** running via Docker Compose quickstart:
  - GMS on `http://localhost:8080`
  - Frontend on `http://localhost:9002`
  - Kafka on `localhost:9092`
  - Schema registry served by GMS at `http://localhost:8080/schema-registry/api/`
- **Python 3.11+** with virtualenv at `code/.venv`
- **Node.js 18+** for the dashboard (dev mode)

### 2. Environment Variables

```bash
cd code
cp .env.example .env
```

Required values in `.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATAHUB_SERVER_URL` | yes | GMS URL (default: `http://localhost:8080`) |
| `DATAHUB_FRONTEND_URL` | yes | Frontend URL (default: `http://localhost:9002`) |
| `DATAHUB_ACCESS_TOKEN` | yes | Personal access token from DataHub UI (Settings > Access Tokens) |
| `DATAHUB_SERVICE_ACCOUNT_TOKEN` | yes | Service account token for MCP server |
| `TOOLS_IS_MUTATION_ENABLED` | yes | Must be `true` for write-back (tags, documents) |
| `SLACK_WEBHOOK_URL` | no | Slack incoming webhook for alerts |
| `GOOGLE_API_KEY` | no | Google Gemini API key for LLM reasoning (or `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) |

### 3. Install Dependencies

```bash
cd code
source .venv/bin/activate
pip install -e .
```

### 4. Verify Test Suite

```bash
python -m pytest tests/ -v
# Expected: all tests pass
```

---

## Step 1: Ingest Sample Data

The healthcare dataset has a forking pipeline with planted quality issues:

```
raw_patients -> staging_patients -> mart_billing
                                -> mart_demographics
```

```bash
cd code/scripts/data

# Ingest tables into DataHub
datahub ingest -c ingest.yaml

# Add lineage relationships
python add_lineage.py

# Add metadata (tags, glossary terms, ownership)
python add_metadata.py

# Create assertions on downstream marts
python create_assertions.py
```

### Verify in DataHub UI

1. Open `http://localhost:9002`
2. Search for `mart_billing` — confirm dataset exists with lineage tab showing upstream chain
3. Search for `mart_demographics` — confirm dataset exists with lineage tab
4. Click on `mart_billing` > Assertions tab — confirm `billingAmountPositive` assertion exists
5. Click on `mart_demographics` > Assertions tab — confirm `patientNameNotNull` and `ageValidRange` assertions exist

---

## Step 2: Start the Agent

The agent process starts both the FastAPI API server (port 8000) and the DataHub Actions Kafka listener in a single command. The MCP server runs in-process — no separate startup needed.

```bash
cd code
source .venv/bin/activate
python -m src.main
```

### Verify

- Console should show:
  ```
  [INFO] __main__: API server started on port 8000
  [INFO] __main__: Starting DataHub Actions listener with config: .../actions_config.yaml
  [INFO] __main__: Waiting for assertion failure events... (Ctrl+C to stop)
  ```
- DataHub Actions pipeline starts:
  ```
  Action Pipeline with name 'incident_response' is now running.
  ```

### Health check

```bash
curl http://localhost:8000/health
# {"status":"ok","uptime_seconds":...}
```

---

## Step 3: Start the Dashboard

```bash
cd code/dashboard
npm install
npm run dev
```

The dashboard is available at `http://localhost:3000`.

### Verify

1. Open `http://localhost:3000` in your browser
2. You should see two tabs: **Incidents** and **Manage**
3. The Incidents tab should show an empty feed (no incidents yet)
4. Click **Manage** > **Agent Control** — confirm agent status shows **running**

---

## Step 4: Create an Assertion (via Dashboard UI)

1. Open `http://localhost:3000` > **Manage** tab > **Assertions** sub-tab
2. The existing assertions from DataHub should appear in the list
3. To create a new one, fill in the form:
   - **Assertion ID**: `myTestAssertion`
   - **Dataset URN**: `urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.mart_billing,PROD)`
   - **Operator**: `GREATER_THAN`
   - **Type**: `DATASET_ROWS`
4. Click **Create Assertion**
5. The new assertion appears in the list above

### Verify via API

```bash
curl http://localhost:8000/manage/assertions | python3 -m json.tool
# Should list all assertions including the one you just created
```

### Verify in DataHub UI

1. Open `http://localhost:9002`
2. Search for `mart_billing` > Assertions tab
3. Confirm the new assertion appears

---

## Step 5: Trigger a Test Failure (via Dashboard UI)

1. In `http://localhost:3000` > **Manage** > **Assertions** sub-tab
2. Scroll to the **Trigger Test Failure** section
3. Fill in:
   - **Assertion URN**: `urn:li:assertion:billingAmountPositive`
   - **Dataset URN**: `urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.mart_billing,PROD)`
   - **Actual Value**: `-42.5` (a negative value to simulate a failure)
4. Click **Trigger Failure**
5. The API emits an `assertionRunEvent` with `result.type=FAILURE` to DataHub, which publishes it to Kafka

### Alternative: Trigger via API

```bash
curl -X POST http://localhost:8000/manage/assertions/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "assertion_urn": "urn:li:assertion:billingAmountPositive",
    "dataset_urn": "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.mart_billing,PROD)",
    "actual_value": "-42.5"
  }'
# {"status":"emitted","assertion_urn":"urn:li:assertion:billingAmountPositive","run_id":"trigger-..."}
```

### Alternative: Trigger via CLI script

```bash
cd code
source .venv/bin/activate
python scripts/trigger_assertion.py
```

---

## Step 6: Observe the Incident Response

### 6.1 Watch the Dashboard

1. Go to `http://localhost:3000` > **Incidents** tab
2. Within a few seconds, a new incident appears in the feed:
   - **Assertion**: `urn:li:assertion:billingAmountPositive`
   - **Dataset**: `healthcare.main.mart_billing`
   - **Status**: Starts as `active`
3. The agent pipeline runs automatically in the background:
   - **Tracer**: Finds upstream dataset candidates via lineage
   - **Checker**: Validates candidates using metadata and LLM analysis
   - **Notifier**: Generates Slack alert (if webhook configured)
   - **Reporter**: Creates an incident report
4. When complete, the incident status transitions to `resolved`
5. Click on the incident to expand details:
   - **Root causes**: Confirmed candidates with confidence scores and reasoning
   - **Agent results**: Full output from each pipeline stage
   - **Elapsed time**: How long the full analysis took

### 6.2 Monitor Agent Logs

The agent process logs to stdout (or `/tmp/agent.log` if run with `nohup`):

```
[INFO] src.datahub_actions_plugin.plugin: Assertion failure detected: IncidentEvent(...)
[INFO] src.coordinator: === Coordinator handling incident: ... ===
[INFO] src.agents.tracer: Tracing upstream lineage for urn:li:dataset:...
[INFO] src.agents.checker: Validating candidate: urn:li:dataset:...raw_patients
[INFO] src.agents.notifier: Sending Slack alert for incident on mart_billing
[INFO] src.agents.reporter: Generating incident report
[INFO] src.coordinator: Incident response result: {...}
```

### 6.3 Verify via API

```bash
# List all incidents
curl http://localhost:8000/incidents | python3 -m json.tool

# Get a specific incident by ID
curl http://localhost:8000/incidents/{id} | python3 -m json.tool
```

The incident JSON includes:
- `status` — `active` or `resolved`
- `root_causes` — array of validated candidates with `candidate_urn`, `status`, `confidence`, `reasoning`, `evidence`
- `agent_results` — full output from `tracer`, `checker`, `notifier`, `reporter`
- `elapsed_seconds` — total pipeline duration
- `created_at` / `resolved_at` — timestamps

### 6.4 Verify in DataHub UI

1. Navigate to `mart_billing` > Documents tab — confirm incident report document appears
2. Navigate to `raw_patients` > Tags tab — confirm `incident-root-cause` tag is present
3. Navigate to `raw_patients` > About tab — confirm description includes incident report reference

---

## Step 7: Configure Alert Routing (Optional)

1. In `http://localhost:3000` > **Manage** > **Config & Routing** sub-tab
2. View current routing rules and Slack webhook configuration
3. Update fields as needed:
   - **Default webhook URL** — Slack incoming webhook for general alerts
   - **Critical webhook URL** — Separate webhook for critical platform alerts
   - **High priority webhook URL** — Webhook for high-confidence incidents
   - **Dedup window** — Seconds before duplicate incidents are suppressed (default: 900)
4. Click **Save** to persist changes

### Environment Variables for Routing

| Variable | Description |
|----------|-------------|
| `SLACK_WEBHOOK_URL` | Default Slack webhook |
| `SLACK_CRITICAL_WEBHOOK_URL` | Critical platform alerts |
| `SLACK_HIGH_PRIORITY_WEBHOOK_URL` | High-confidence incidents |

---

## Step 8: Agent Lifecycle Control (via Dashboard UI)

1. In `http://localhost:3000` > **Manage** > **Agent Control** sub-tab
2. **Status** — shows current agent PID, uptime, and running state
3. **Restart** — restarts the DataHub Actions listener (use after config changes)
4. **Stop** — gracefully shuts down the agent

### Via API

```bash
# Check status
curl http://localhost:8000/manage/agent/status

# Restart
curl -X POST http://localhost:8000/manage/agent/restart

# Stop
curl -X POST http://localhost:8000/manage/agent/stop
```

---

## Edge Case Verification

### No Root Cause Found

1. Trigger an assertion failure on a dataset with clean upstream nodes
2. Verify:
   - Tracer returns empty or low-confidence candidates
   - Checker rejects all candidates (below threshold)
   - Notifier sends alert with "no root cause identified"
   - Reporter writes report with "investigation inconclusive" recommendation

### MCP Server Timeouts

The MCP client retries with exponential backoff (up to 3 attempts). If all retries fail, the agent falls back to direct GraphQL queries against DataHub GMS. The pipeline continues with partial results.

### LLM API Unavailable

1. Set an invalid `GOOGLE_API_KEY` (or no key at all)
2. Trigger an assertion failure
3. Verify:
   - Checker falls back to heuristic-only mode
   - No crash, no hang
   - Validation results still produced (without LLM reasoning enrichment)

### Slack Webhook Down

1. Set an invalid `SLACK_WEBHOOK_URL`
2. Trigger an assertion failure
3. Verify:
   - Notifier logs error but does not crash
   - Pipeline continues to Reporter
   - Report is still written to DataHub

### Deduplication

1. Trigger the same assertion failure twice within the dedup window (default: 900 seconds)
2. Verify:
   - First trigger creates a new incident
   - Second trigger is suppressed with log: `Duplicate incident suppressed`
   - Only one incident appears in the dashboard

---

## Troubleshooting

### Pipeline not triggering

- Check DataHub is running: `curl http://localhost:8080/health`
- Check agent is running: `curl http://localhost:8000/manage/agent/status`
- Check Kafka topics exist:
  ```bash
  docker exec datahub-kafka-broker-1 kafka-topics --list --bootstrap-server localhost:9092
  ```
- Verify the assertion event was emitted to Kafka:
  ```bash
  docker exec datahub-kafka-broker-1 kafka-console-consumer \
    --bootstrap-server localhost:9092 \
    --topic MetadataChangeLog_Timeseries_v1 \
    --from-beginning --max-messages 5
  ```
- Check agent logs for event reception and filter results
- Note: The Kafka consumer uses `auto.offset.reset: latest`, so events must be triggered AFTER the agent starts

### Assertions not listing in dashboard

- The `GET /manage/assertions` endpoint queries DataHub's GraphQL API
- Verify DataHub has assertions: search for "assertion" in DataHub UI
- Check the agent API can reach DataHub: `curl http://localhost:8000/manage/assertions`

### Tracer finds no candidates

- Verify lineage exists: check DataHub UI > dataset > Lineage tab
- Look for MCPClient timeout/retry warnings in agent logs
- The tracer falls back to direct GraphQL if MCP times out

### Checker rejects all candidates

- Check confidence threshold in `config/agent_config.yaml` (default: 0.5)
- Verify candidate metadata is accessible via DataHub
- If using LLM: check API key is valid and not rate-limited

### Reporter fails to write back

- Verify `TOOLS_IS_MUTATION_ENABLED=true` in `.env`
- Check `DATAHUB_ACCESS_TOKEN` has write permissions
- Look for error logs from the Reporter agent

### Dashboard not loading

- Verify the dev server is running: `curl http://localhost:3000`
- Check the agent API is reachable: `curl http://localhost:8000/health`
- The dashboard polls the API at `http://localhost:8000` by default

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Liveness probe with uptime |
| `/metrics` | GET | Prometheus-style metrics |
| `/incidents` | GET | List incidents (optional `?status=active&limit=50`) |
| `/incidents/{id}` | GET | Single incident detail |
| `/stats` | GET | Aggregate metrics (total, active, resolved, avg MTTR) |
| `/manage/assertions` | GET | List assertions from DataHub |
| `/manage/assertions` | POST | Create a new dataset assertion |
| `/manage/assertions/trigger` | POST | Emit a test assertion failure event |
| `/manage/config` | GET | View agent config and alert routing |
| `/manage/config/routing` | PUT | Update alert routing rules and Slack config |
| `/manage/agent/status` | GET | Check if Actions listener is running |
| `/manage/agent/restart` | POST | Restart the DataHub Actions listener |
| `/manage/agent/stop` | POST | Stop the Actions listener |
