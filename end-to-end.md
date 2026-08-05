# End-to-End Manual Verification Guide

Detailed steps to verify the full Data Incident Response Agent pipeline against a live DataHub instance.

---

## Prerequisites

### 1. Infrastructure

- DataHub running (GMS on `localhost:8080`, frontend on `localhost:9002`)
- Kafka running (default `localhost:9092`, schema registry `localhost:8081`)
- DataHub MCP Server running (default `localhost:8000`)
- Python 3.12+ with virtualenv at `code/.venv`

### 2. Environment Variables

Copy `.env.example` to `.env` and fill in:

```bash
cd code
cp .env.example .env
```

Required values:
- `DATAHUB_SERVER_URL` — GMS URL (e.g., `http://localhost:8080`)
- `DATAHUB_ACCESS_TOKEN` — Personal access token from DataHub UI (Settings > Access Tokens)
- `TOOLS_DATAHUB_API_TOKEN` — Same token, used by MCP Server
- `TOOLS_IS_MUTATION_ENABLED=true` — Required for write-back (tags, documents, descriptions)
- `SLACK_WEBHOOK_URL` — Slack incoming webhook for alerts (optional but recommended)
- `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` — LLM API key (optional — falls back to heuristic-only mode)

### 3. Install Dependencies

```bash
cd code
source .venv/bin/activate
pip install -e .
```

### 4. Verify Test Suite

```bash
python -m pytest tests/ -v
# Expected: 92 tests pass
```

---

## Step 1: Ingest Sample Data

The healthcare dataset has a forking pipeline with planted quality issues:

```
raw_patients → staging_patients → mart_billing
                                → mart_demographics
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

## Step 2: Start the MCP Server

The MCP Server provides tools that agents use to query DataHub.

```bash
# Follow DataHub MCP Server setup instructions
# Typically runs on http://localhost:8000
```

### Verify MCP Server

```bash
cd code/scripts
python test_mcp_tools.py
# Should list available tools: search, get_lineage, get_entities, etc.
```

---

## Step 3: Start the DataHub Actions Listener

This listens for assertion run events on Kafka and triggers the incident response pipeline.

```bash
cd code
source .venv/bin/activate

# Start the actions listener
datahub actions -c config/actions_config.yaml
```

### Verify

- Console should show: `Action 'incident_response' started`
- No errors in output

---

## Step 4: Trigger an Assertion Failure

### Option A: Run Assertions via DataHub UI

1. Open DataHub UI (`http://localhost:9002`)
2. Navigate to `mart_billing` > Assertions tab
3. Click on `billingAmountPositive` assertion
4. Trigger a run (if Cloud) or use `datahub` CLI to report a failure

### Option B: Report Assertion Failure via CLI

```bash
# Report a failed assertion result for billingAmountPositive on mart_billing
datahub assertion run-result \
  --urn "urn:li:assertion:..." \
  --status FAILED \
  --result-type FAIL
```

### Option C: Insert Bad Data and Re-run

```bash
# Insert a negative billing amount to trigger the assertion
sqlite3 scripts/data/healthcare.db \
  "UPDATE mart_billing SET billing_amount = -999.99 WHERE rowid = 1"

# Re-ingest the table so DataHub sees the bad data
cd scripts/data
datahub ingest -c ingest.yaml
```

---

## Step 5: Observe the Pipeline

When the assertion failure event reaches the Actions listener, the pipeline executes:

### 5.1 Coordinator Receives Event

Watch the console for:
```
[INFO] src.coordinator: Received incident: assertion=urn:li:assertion:... dataset=urn:li:dataset:...
[INFO] src.coordinator: Dispatching tracer for task: investigate_incident:...
```

### 5.2 Tracer Agent

```
[INFO] src.agents.tracer: Tracing upstream lineage for urn:li:dataset:...
[INFO] src.agents.tracer: Found N upstream nodes
[INFO] src.agents.tracer: Evaluating node: urn:li:dataset:...raw_patients
[INFO] src.agents.tracer: Candidate: raw_patients (confidence=0.X)
```

**Verify:**
- Tracer should find `raw_patients` as a candidate root cause (it has the planted quality issues)
- `staging_patients` may also appear as a candidate with lower confidence
- Candidates should be sorted by confidence (highest first)

### 5.3 Checker Agent

```
[INFO] src.agents.checker: Validating candidate: urn:li:dataset:...raw_patients
[INFO] src.agents.checker: Candidate has failed assertions: True
[INFO] src.agents.checker: Validation result: confirmed (confidence=0.X)
```

**Verify:**
- If LLM API key is set: Checker should show `LLM: <reasoning>` in the validation reasoning
- If no LLM key: Checker falls back to heuristic-only mode (still works, just no LLM enrichment)
- `raw_patients` should be confirmed or probable (it has the source quality issues)
- Confidence should be >= 0.5 (the probable threshold)

### 5.4 Notifier Agent

```
[INFO] src.agents.notifier: Sending Slack alert for incident on mart_billing
[INFO] src.agents.notifier: Alert sent successfully (or: Slack webhook not configured)
```

**Verify:**
- If `SLACK_WEBHOOK_URL` is set: check Slack channel `#data-incidents` for an alert
- Alert should contain: dataset name, assertion name, error message, root cause candidates
- If webhook not configured: pipeline continues (graceful degradation)

### 5.5 Reporter Agent

```
[INFO] src.agents.reporter: Generating incident report
[INFO] src.agents.reporter: Incident report saved to DataHub: urn:li:document:...
[INFO] src.agents.reporter: Tagged N root cause datasets
[INFO] src.agents.reporter: Updated description for urn:li:dataset:...raw_patients
```

**Verify in DataHub UI:**
1. Navigate to `mart_billing` > Documents tab — confirm incident report document appears
2. Navigate to `raw_patients` > Tags tab — confirm `incident-root-cause` tag is present
3. Navigate to `raw_patients` > About tab — confirm description includes incident report reference

### 5.6 Coordinator Summary

```
[INFO] src.coordinator: Incident response result: {
  'tracer': {'status': 'completed', 'candidates': [...]},
  'checker': {'status': 'completed', 'validated_candidates': [...]},
  'notifier': {'status': 'completed'},
  'reporter': {'status': 'completed', 'document_urn': 'urn:li:document:...'}
}
```

---

## Step 6: Verify Report Content

Open the incident report document in DataHub UI and check it contains:

- [ ] **Incident Summary** — dataset name, assertion name, error message, timestamp
- [ ] **Root Cause Analysis** — validated root cause(s) with confidence scores and reasoning
- [ ] **Lineage Path** — chain from root cause to failing dataset (e.g., `raw_patients → staging_patients → mart_billing`)
- [ ] **Affected Datasets** — all datasets in the lineage path
- [ ] **Recommended Actions** — suggestions based on root cause type
- [ ] **Incident Metadata** — timestamp, agent version, tools used

---

## Step 7: Edge Case Verification

### 7.1 No Root Cause Found

1. Trigger an assertion failure on a dataset with clean upstream nodes
2. Verify:
   - Tracer returns empty or low-confidence candidates
   - Checker rejects all candidates (below threshold)
   - Notifier sends alert with "no root cause identified"
   - Reporter writes report with "investigation inconclusive" recommendation

### 7.2 MCP Server Unavailable

1. Stop the MCP Server
2. Trigger an assertion failure
3. Verify:
   - Tracer fails gracefully with error message
   - Pipeline does not crash
   - Coordinator logs the failure and continues to next agent

### 7.3 LLM API Unavailable

1. Set an invalid `ANTHROPIC_API_KEY` (or no key at all)
2. Trigger an assertion failure
3. Verify:
   - Checker falls back to heuristic-only mode
   - No crash, no hang
   - Validation results still produced (without LLM reasoning enrichment)

### 7.4 Slack Webhook Down

1. Set an invalid `SLACK_WEBHOOK_URL`
2. Trigger an assertion failure
3. Verify:
   - Notifier logs error but does not crash
   - Pipeline continues to Reporter
   - Report is still written to DataHub

### 7.5 Timeout Handling

1. Configure a very slow MCP Server response (or reduce `AGENT_TIMEOUT_SECONDS=5`)
2. Trigger an assertion failure
3. Verify:
   - MCPClient retries with exponential backoff (up to 3 attempts)
   - After retries exhausted, agent fails gracefully
   - Pipeline continues with partial results

---

## Step 8: Run Automated Tests

```bash
cd code
source .venv/bin/activate

# Full suite
python -m pytest tests/ -v

# By module
python -m pytest tests/test_actions_plugin.py -v   # 16 tests — Actions plugin
python -m pytest tests/test_coordinator.py -v       #  9 tests — Coordinator
python -m pytest tests/test_tracer.py -v            # 11 tests — Tracer agent
python -m pytest tests/test_checker.py -v           #  8 tests — Checker agent
python -m pytest tests/test_notifier_reporter.py -v # 12 tests — Notifier + Reporter
python -m pytest tests/test_e2e.py -v               #  9 tests — E2E pipeline
python -m pytest tests/test_llm.py -v               # 13 tests — LLM integration
python -m pytest tests/test_edge_cases.py -v        #  9 tests — Edge cases
python -m pytest tests/test_skills.py -v            #  6 tests — Skills loader
```

---

## Troubleshooting

### Pipeline not triggering

- Check Kafka is running: `kafka-topics --list --bootstrap-server localhost:9092`
- Check DataHub Actions is running and listening
- Verify the assertion event was emitted: check DataHub > Ingestion > Events
- Ensure `config/actions_config.yaml` filter matches `assertionRunEvent`

### Tracer finds no candidates

- Verify lineage exists: `datahub lineage --urn "urn:li:dataset:..." --direction upstream`
- Check MCP Server is running and responding
- Look for MCPClient timeout/retry warnings in logs

### Checker rejects all candidates

- Check confidence threshold in `config/agent_config.yaml` (default: 0.5)
- Verify candidate metadata is accessible via MCP Server
- If using LLM: check API key is valid and not rate-limited

### Reporter fails to write back

- Verify `TOOLS_IS_MUTATION_ENABLED=true` in `.env`
- Check `DATAHUB_ACCESS_TOKEN` has write permissions
- Verify MCP Server supports `save_document`, `add_tags`, `update_description` tools

### Slack alert not sent

- Verify `SLACK_WEBHOOK_URL` is set and valid
- Check network connectivity to Slack API
- Look for error logs from Notifier agent
