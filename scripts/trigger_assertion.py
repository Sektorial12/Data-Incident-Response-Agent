"""Trigger a real assertion failure event in DataHub to test the agent end-to-end.

Usage:
    cd code && python scripts/trigger_assertion.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.emitter.rest_emitter import DataHubRestEmitter
from datahub.metadata.schema_classes import (
    AssertionResultClass,
    AssertionResultTypeClass,
    AssertionRunEventClass,
    AssertionRunStatusClass,
)

DATAHUB_URL = os.getenv("DATAHUB_SERVER_URL", "http://localhost:8080")
TOKEN = os.getenv("DATAHUB_ACCESS_TOKEN", "")

assertion_urn = "urn:li:assertion:billingAmountPositive"
dataset_urn = "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.mart_billing,PROD)"
run_id = f"incident-test-{int(time.time())}"
timestamp_ms = int(time.time() * 1000)

event = AssertionRunEventClass(
    assertionUrn=assertion_urn,
    asserteeUrn=dataset_urn,
    runId=run_id,
    timestampMillis=timestamp_ms,
    status=AssertionRunStatusClass.COMPLETE,
    result=AssertionResultClass(
        type=AssertionResultTypeClass.FAILURE,
        rowCount=1500,
        actualAggValue=-42.50,
    ),
)

mcp = MetadataChangeProposalWrapper(
    entityUrn=assertion_urn,
    aspect=event,
)

emitter = DataHubRestEmitter(gms_server=DATAHUB_URL, token=TOKEN)
emitter.emit_mcp(mcp)

print(f"Emitted assertion FAILURE event!")
print(f"  Assertion: {assertion_urn}")
print(f"  Dataset:   {dataset_urn}")
print(f"  Run ID:    {run_id}")
print(f"  Timestamp: {timestamp_ms}")
print()
print("The agent should pick this up from Kafka within a few seconds.")
print("Watch the dashboard at http://localhost:3000")
