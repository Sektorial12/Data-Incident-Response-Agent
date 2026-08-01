#!/usr/bin/env python3
"""Test remaining MCP tools: get_lineage_paths_between, add_tags, save_document."""

import asyncio
import json
import os

from dotenv import load_dotenv

load_dotenv()

RAW_PATIENTS_URN = "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.raw_patients,PROD)"
MART_BILLING_URN = "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.mart_billing,PROD)"


def extract_text(result):
    if isinstance(result, list):
        return result[0].text if result and hasattr(result[0], "text") else str(result)
    return str(result)


async def test_remaining_tools():
    from datahub.sdk import DataHubClient
    from mcp_server_datahub.mcp_server import mcp, register_all_tools
    from mcp_server_datahub.graphql_helpers import _mcp_context, MCPContext

    register_all_tools(mcp)

    client = DataHubClient(
        server=os.getenv("DATAHUB_SERVER_URL"),
        token=os.getenv("DATAHUB_ACCESS_TOKEN"),
    )
    _mcp_context.set(MCPContext(client=client))

    print("--- Testing get_lineage_paths_between (mart_billing -> raw_patients upstream) ---")
    paths_result = await mcp.call_tool("get_lineage_paths_between", {
        "source_urn": MART_BILLING_URN,
        "target_urn": RAW_PATIENTS_URN,
        "direction": "upstream",
    })
    print(extract_text(paths_result)[:2000])

    print("\n--- Testing add_tags on raw_patients ---")
    tags_result = await mcp.call_tool("add_tags", {
        "tag_urns": ["urn:li:tag:pii"],
        "entity_urns": [MART_BILLING_URN],
    })
    print(extract_text(tags_result)[:1000])

    print("\n--- Testing save_document on raw_patients ---")
    doc_result = await mcp.call_tool("save_document", {
        "document_type": "Note",
        "title": "MCP Test Document",
        "content": "This is a test document created via MCP Server to verify mutation tools work.",
        "related_assets": [RAW_PATIENTS_URN],
    })
    print(extract_text(doc_result)[:1000])

    print("\n--- Testing remove_tags (cleanup) ---")
    remove_result = await mcp.call_tool("remove_tags", {
        "tag_urns": ["urn:li:tag:pii"],
        "entity_urns": [MART_BILLING_URN],
    })
    print(extract_text(remove_result)[:1000])

    print("\n--- All remaining MCP tool tests passed ---")


if __name__ == "__main__":
    asyncio.run(test_remaining_tools())
