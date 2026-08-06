"""Management API — assertion creation, config, agent lifecycle."""

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import requests
import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/manage", tags=["management"])

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "agent_config.yaml"
_agent_proc: subprocess.Popen | None = None
_agent_started_at: float = 0.0


def set_agent_proc(proc: subprocess.Popen | None) -> None:
    global _agent_proc, _agent_started_at
    _agent_proc = proc
    _agent_started_at = time.time() if proc else 0.0


class CreateAssertionRequest(BaseModel):
    assertion_id: str = Field(..., description="Short ID")
    dataset_urn: str = Field(..., description="Full dataset URN")
    type: str = Field("DATASET_ROWS")
    operator: str = Field("EQUAL_TO")


class TriggerFailureRequest(BaseModel):
    assertion_urn: str = Field(...)
    dataset_urn: str = Field(...)
    error_message: str = Field("Manual trigger from dashboard")
    actual_value: float = Field(-42.50)


class UpdateRoutingRequest(BaseModel):
    rules: list[dict[str, Any]] = Field(default_factory=list)
    default_webhook_url: str = ""
    dedup_window_seconds: int = 900


def _datahub_headers() -> dict[str, str]:
    token = os.getenv("DATAHUB_ACCESS_TOKEN", "")
    return {"Authorization": f"Bearer {token}"} if token else {}


@router.get("/assertions")
def list_assertions() -> dict[str, Any]:
    url = os.getenv("DATAHUB_SERVER_URL", "http://localhost:8080")
    query = '{searchAcrossEntities(input:{types:[ASSERTION],query:"*",start:0,count:50}){searchResults{entity{urn type ...on Assertion{info{type datasetAssertion{datasetUrn scope operator}}}}}}}'
    try:
        resp = requests.post(f"{url}/api/graphql", json={"query": query}, headers=_datahub_headers(), timeout=15)
        resp.raise_for_status()
        body = resp.json()
        results = (body.get("data") or {}).get("searchAcrossEntities", {}) or {}
        results = results.get("searchResults", []) or []
        assertions = []
        for r in results:
            e = (r or {}).get("entity", {}) or {}
            info = e.get("info", {}) or {}
            da = info.get("datasetAssertion", {}) or {}
            assertions.append({"urn": e.get("urn", ""), "type": info.get("type", ""), "dataset": da.get("datasetUrn", ""), "operator": da.get("operator", "")})
        return {"assertions": assertions, "total": len(assertions)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/assertions")
def create_assertion(req: CreateAssertionRequest) -> dict[str, Any]:
    from datahub.emitter.mcp import MetadataChangeProposalWrapper
    from datahub.emitter.rest_emitter import DataHubRestEmitter
    from datahub.metadata.schema_classes import (
        AssertionInfoClass, DatasetAssertionInfoClass,
        AssertionTypeClass, DatasetAssertionScopeClass, AssertionStdOperatorClass,
    )
    url = os.getenv("DATAHUB_SERVER_URL", "http://localhost:8080")
    token = os.getenv("DATAHUB_ACCESS_TOKEN", "")
    assertion_urn = f"urn:li:assertion:{req.assertion_id}"
    op_map = {"EQUAL_TO": AssertionStdOperatorClass.EQUAL_TO, "NOT_EQUAL_TO": AssertionStdOperatorClass.NOT_EQUAL_TO,
              "GREATER_THAN": AssertionStdOperatorClass.GREATER_THAN, "LESS_THAN": AssertionStdOperatorClass.LESS_THAN}
    op = op_map.get(req.operator.upper(), AssertionStdOperatorClass.EQUAL_TO)
    atype = getattr(AssertionTypeClass, {"DATASET_ROWS": "DATASET", "DATASET_SCHEMA": "DATA_SCHEMA", "FIELD": "FIELD", "FRESHNESS": "FRESHNESS", "VOLUME": "VOLUME", "SQL": "SQL", "CUSTOM": "CUSTOM"}.get(req.type.upper(), "DATASET"), AssertionTypeClass.DATASET)
    try:
        info = DatasetAssertionInfoClass(dataset=req.dataset_urn, scope=DatasetAssertionScopeClass.DATASET_ROWS, operator=op, fields=None, aggregation=None, parameters=None)
        aspect = AssertionInfoClass(type=atype, datasetAssertion=info)
        mcp = MetadataChangeProposalWrapper(entityUrn=assertion_urn, aspect=aspect)
        DataHubRestEmitter(gms_server=url, token=token).emit_mcp(mcp)
        return {"status": "created", "assertion_urn": assertion_urn}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/assertions/trigger")
def trigger_failure(req: TriggerFailureRequest) -> dict[str, Any]:
    from datahub.emitter.mcp import MetadataChangeProposalWrapper
    from datahub.emitter.rest_emitter import DataHubRestEmitter
    from datahub.metadata.schema_classes import (
        AssertionResultClass, AssertionResultTypeClass,
        AssertionRunEventClass, AssertionRunStatusClass,
    )
    url = os.getenv("DATAHUB_SERVER_URL", "http://localhost:8080")
    token = os.getenv("DATAHUB_ACCESS_TOKEN", "")
    run_id = f"trigger-{int(time.time())}"
    try:
        event = AssertionRunEventClass(
            assertionUrn=req.assertion_urn, asserteeUrn=req.dataset_urn,
            runId=run_id, timestampMillis=int(time.time() * 1000),
            status=AssertionRunStatusClass.COMPLETE,
            result=AssertionResultClass(type=AssertionResultTypeClass.FAILURE, rowCount=1500, actualAggValue=float(req.actual_value) if req.actual_value else None),
        )
        mcp = MetadataChangeProposalWrapper(entityUrn=req.assertion_urn, aspect=event)
        DataHubRestEmitter(gms_server=url, token=token).emit_mcp(mcp)
        return {"status": "emitted", "assertion_urn": req.assertion_urn, "run_id": run_id}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/config")
def get_config() -> dict[str, Any]:
    try:
        with open(_CONFIG_PATH) as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        config = {}
    routing = config.get("alert_routing", {})
    return {
        "llm": config.get("llm", {}),
        "lineage": config.get("lineage", {}),
        "confidence": config.get("confidence", {}),
        "timeout": config.get("timeout", {}),
        "agents": config.get("agents", {}),
        "alert_routing": routing,
        "env": {
            "datahub_server_url": os.getenv("DATAHUB_SERVER_URL", ""),
            "datahub_frontend_url": os.getenv("DATAHUB_FRONTEND_URL", ""),
            "slack_webhook_configured": bool(os.getenv("SLACK_WEBHOOK_URL")),
            "llm_provider": next((k for k, v in {"anthropic": os.getenv("ANTHROPIC_API_KEY"), "openai": os.getenv("OPENAI_API_KEY"), "google": os.getenv("GOOGLE_API_KEY")}.items() if v), "none"),
        },
    }


@router.put("/config/routing")
def update_routing(req: UpdateRoutingRequest) -> dict[str, Any]:
    try:
        with open(_CONFIG_PATH) as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        config = {}
    config.setdefault("alert_routing", {})
    config["alert_routing"]["rules"] = req.rules
    config["alert_routing"]["default_webhook_url"] = req.default_webhook_url
    config["alert_routing"]["dedup_window_seconds"] = req.dedup_window_seconds
    with open(_CONFIG_PATH, "w") as f:
        yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
    return {"status": "updated", "rules_count": len(req.rules)}


@router.get("/agent/status")
def agent_status() -> dict[str, Any]:
    if _agent_proc and _agent_proc.poll() is None:
        return {"status": "running", "pid": _agent_proc.pid, "uptime_seconds": round(time.time() - _agent_started_at, 1)}
    return {"status": "stopped", "pid": None, "uptime_seconds": 0}


@router.post("/agent/restart")
def agent_restart() -> dict[str, Any]:
    global _agent_proc, _agent_started_at
    if _agent_proc and _agent_proc.poll() is None:
        _agent_proc.terminate()
        try:
            _agent_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _agent_proc.kill()
    config_path = Path(__file__).parent.parent.parent / "config" / "actions_config.yaml"
    try:
        _agent_proc = subprocess.Popen(["datahub", "actions", "-c", str(config_path)], env=os.environ.copy())
        _agent_started_at = time.time()
        return {"status": "restarted", "pid": _agent_proc.pid}
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="datahub CLI not found")


@router.post("/agent/stop")
def agent_stop() -> dict[str, Any]:
    global _agent_proc
    if _agent_proc and _agent_proc.poll() is None:
        _agent_proc.terminate()
        try:
            _agent_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _agent_proc.kill()
        return {"status": "stopped"}
    return {"status": "already_stopped"}
