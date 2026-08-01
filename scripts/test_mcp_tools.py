#!/usr/bin/env python3
"""Test MCP Server tools against the running DataHub instance."""

import asyncio
import json
import os

from dotenv import load_dotenv

load_dotenv()

MART_BILLING_URN = "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.mart_billing,PROD)"
RAW_PATIENTS_URN = "urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.raw_patients,PROD)"


async def test_mcp_tools():
    from datahub.sdk import DataHubClient
    from mcp_server_datahub.mcp_server import mcp, register_all_tools, set_datahub_client
    from mcp_server_datahub.graphql_helpers import _mcp_context, MCPContext

    register_all_tools(mcp)

    client = DataHubClient(
        server=os.getenv("DATAHUB_SERVER_URL"),
        token=os.getenv("DATAHUB_ACCESS_TOKEN"),
    )
    ctx = MCPContext(client=client)
    _mcp_context.set(ctx)

    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    print(f"Registered tools ({len(tool_names)}):")
    for name in sorted(tool_names):
        print(f"  - {name}")

    mutation_tools = [t for t in tools if any(k in t.name for k in ("save", "add", "update", "remove", "set"))]
    print(f"\nMutation tools ({len(mutation_tools)}):")
    for t in mutation_tools:
        print(f"  - {t.name}")

    def extract_text(result):
        if isinstance(result, list):
            return result[0].text if result and hasattr(result[0], "text") else str(result)
        return str(result)

    print("\n--- Testing search ---")
    search_result = await mcp.call_tool("search", {"query": "healthcare", "num_results": 10})
    print(extract_text(search_result)[:2000])

    print("\n--- Testing get_lineage (UPSTREAM from mart_billing) ---")
    lineage_result = await mcp.call_tool("get_lineage", {
        "urn": MART_BILLING_URN,
        "upstream": True,
        "max_hops": 3,
    })
    print(extract_text(lineage_result)[:2000])

    print("\n--- Testing get_entities ---")
    entities_result = await mcp.call_tool("get_entities", {"urns": [RAW_PATIENTS_URN]})
    print(extract_text(entities_result)[:2000])

    print("\n--- Testing list_schema_fields ---")
    schema_result = await mcp.call_tool("list_schema_fields", {"urn": RAW_PATIENTS_URN})
    print(extract_text(schema_result)[:2000])

    print("\n--- All MCP tool tests passed ---")


if __name__ == "__main__":
    asyncio.run(test_mcp_tools())
