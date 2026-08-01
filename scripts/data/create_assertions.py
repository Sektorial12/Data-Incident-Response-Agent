#!/usr/bin/env python3
"""Create data quality assertions on healthcare datasets in DataHub.

These assertions are what our Incident Response Agent will monitor.
When an assertion fails, the agent traces lineage to find root cause.

Run AFTER ingestion + lineage + metadata:
    python create_assertions.py

Supports: --dry-run
"""

import sys

from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.emitter.rest_emitter import DatahubRestEmitter
from datahub.ingestion.graph.client import DataHubGraph, DatahubClientConfig
from datahub.metadata.schema_classes import (
    AssertionInfoClass,
    AssertionTypeClass,
    DatasetAssertionInfoClass,
    DatasetAssertionScopeClass,
    AssertionStdOperatorClass,
    AssertionStdAggregationClass,
    AssertionStdParametersClass,
    AssertionStdParameterClass,
    AssertionStdParameterTypeClass,
)

DATAHUB_SERVER = "http://localhost:8080"

ASSERTIONS = [
    {
        "name": "billingAmountPositive",
        "description": "Billing amount (field: billing_amount) must always be positive. Negative values indicate data entry errors.",
        "dataset": "mart_billing",
        "operator": AssertionStdOperatorClass.GREATER_THAN,
        "aggregation": AssertionStdAggregationClass.MIN,
        "parameters": AssertionStdParametersClass(
            value=AssertionStdParameterClass(value="0", type=AssertionStdParameterTypeClass.NUMBER),
        ),
    },
    {
        "name": "patientNameNotNull",
        "description": "Patient name (field: name) must not be NULL. NULL names indicate incomplete records.",
        "dataset": "mart_demographics",
        "operator": AssertionStdOperatorClass.NOT_NULL,
        "aggregation": AssertionStdAggregationClass.IDENTITY,
        "parameters": None,
    },
    {
        "name": "ageValidRange",
        "description": "Patient age (field: age) must be between 0 and 120. Values outside this range are impossible.",
        "dataset": "mart_demographics",
        "operator": AssertionStdOperatorClass.BETWEEN,
        "aggregation": AssertionStdAggregationClass.MIN,
        "parameters": AssertionStdParametersClass(
            minValue=AssertionStdParameterClass(value="0", type=AssertionStdParameterTypeClass.NUMBER),
            maxValue=AssertionStdParameterClass(value="120", type=AssertionStdParameterTypeClass.NUMBER),
        ),
    },
    {
        "name": "admissionBeforeDischarge",
        "description": "Date of admission (field: date_of_admission) must precede discharge date (field: discharge_date). Swapped dates indicate a pipeline bug.",
        "dataset": "mart_billing",
        "operator": AssertionStdOperatorClass.LESS_THAN,
        "aggregation": AssertionStdAggregationClass.MAX,
        "parameters": AssertionStdParametersClass(
            value=AssertionStdParameterClass(value="discharge_date", type=AssertionStdParameterTypeClass.STRING),
        ),
    },
]


def discover_urns(graph):
    query = """
    { search(input: {type: DATASET, query: "healthcare", start: 0, count: 100}) {
        searchResults { entity { urn ... on Dataset { name platform { name } } } } } }
    """
    result = graph.execute_graphql(query)
    urn_map = {}
    for item in result.get("search", {}).get("searchResults", []):
        entity = item.get("entity", {})
        if entity.get("platform", {}).get("name", "") != "sqlite":
            continue
        if "healthcare" not in entity.get("urn", ""):
            continue
        name = entity.get("name", "")
        simple = name.split(".")[-1] if "." in name else name
        urn_map[simple] = entity["urn"]
    return urn_map


def create_assertions(emitter, urn_map, dry_run=False):
    count = 0
    for a in ASSERTIONS:
        dataset_urn = urn_map.get(a["dataset"])
        if not dataset_urn:
            print(f"  SKIP {a['name']}: dataset '{a['dataset']}' not found")
            continue

        assertion_urn = f"urn:li:assertion:{a['name']}"

        if dry_run:
            print(f"  DRY RUN: {a['name']} on {a['dataset']}")
            count += 1
            continue

        emitter.emit(MetadataChangeProposalWrapper(
            entityUrn=assertion_urn,
            aspect=AssertionInfoClass(
                type=AssertionTypeClass.DATASET,
                datasetAssertion=DatasetAssertionInfoClass(
                    dataset=dataset_urn,
                    scope=DatasetAssertionScopeClass.DATASET_ROWS,
                    operator=a["operator"],
                    aggregation=a["aggregation"],
                    parameters=a["parameters"],
                ),
                description=a["description"],
            ),
        ))
        print(f"  OK {a['name']} on {a['dataset']}")
        count += 1

    return count


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"Connecting to DataHub at {DATAHUB_SERVER}...")
    try:
        graph = DataHubGraph(DatahubClientConfig(server=DATAHUB_SERVER))
    except Exception as e:
        print(f"  Cannot connect: {e}")
        sys.exit(1)

    emitter = DatahubRestEmitter(DATAHUB_SERVER)

    urn_map = discover_urns(graph)
    if not urn_map:
        print("  No datasets found. Run ingestion first.")
        sys.exit(1)

    print(f"  Found {len(urn_map)} datasets")

    print(f"\n  Creating assertions...")
    count = create_assertions(emitter, urn_map, dry_run=dry_run)

    print(f"\n{'='*50}")
    if dry_run:
        print(f"DRY RUN - {count} assertions would be created")
    else:
        print(f"Assertions created: {count}")
        print(f"  - billingAmountPositive (mart_billing)")
        print(f"  - patientNameNotNull (mart_demographics)")
        print(f"  - ageValidRange (mart_demographics)")
        print(f"  - admissionBeforeDischarge (mart_billing)")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
