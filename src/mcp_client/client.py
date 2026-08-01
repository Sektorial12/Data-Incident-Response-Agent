"""MCP Client wrapper — sync interface to the DataHub MCP Server tools."""

import asyncio
import json
import logging
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class MCPClient:
    """Synchronous wrapper around the MCP Server tools.

    Initializes the MCP context once and provides a simple call_tool interface
    for agents to use.
    """

    def __init__(
        self,
        server_url: str | None = None,
        token: str | None = None,
    ) -> None:
        self.server_url = server_url or os.getenv("DATAHUB_SERVER_URL", "http://localhost:8080")
        self.token = token or os.getenv("DATAHUB_ACCESS_TOKEN", "")
        self._client = None
        self._mcp = None
        self._loop = None
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        from datahub.sdk import DataHubClient
        from mcp_server_datahub.graphql_helpers import MCPContext, _mcp_context
        from mcp_server_datahub.mcp_server import mcp, register_all_tools

        register_all_tools(mcp)

        self._client = DataHubClient(
            server=self.server_url,
            token=self.token,
        )
        _mcp_context.set(MCPContext(client=self._client))
        self._mcp = mcp
        self._loop = asyncio.new_event_loop()
        self._initialized = True
        logger.info("MCPClient initialized — server: %s", self.server_url)

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call an MCP tool by name with the given arguments.

        Args:
            tool_name: Name of the MCP tool (e.g., "search", "get_lineage").
            arguments: Dictionary of tool arguments.

        Returns:
            Parsed JSON result from the tool, or raw text if not JSON.
        """
        self._ensure_initialized()
        self.logger.debug("Calling MCP tool: %s with args: %s", tool_name, arguments)

        try:
            result = self._loop.run_until_complete(
                self._mcp.call_tool(tool_name, arguments)
            )
            return self._extract_result(result)
        except Exception as e:
            self.logger.error("MCP tool %s failed: %s", tool_name, e)
            raise

    def search(self, query: str, num_results: int = 10) -> dict[str, Any]:
        return self.call_tool("search", {"query": query, "num_results": num_results})

    def get_lineage(self, urn: str, direction: str = "UPSTREAM", max_hops: int = 3) -> dict[str, Any]:
        return self.call_tool("get_lineage", {
            "urn": urn,
            "direction": direction,
            "max_hops": max_hops,
        })

    def get_lineage_paths_between(
        self, source_urn: str, target_urn: str, direction: str = "upstream"
    ) -> dict[str, Any]:
        return self.call_tool("get_lineage_paths_between", {
            "source_urn": source_urn,
            "target_urn": target_urn,
            "direction": direction,
        })

    def get_entities(self, urns: list[str]) -> dict[str, Any]:
        return self.call_tool("get_entities", {"urns": urns})

    def list_schema_fields(self, urn: str) -> dict[str, Any]:
        return self.call_tool("list_schema_fields", {"urn": urn})

    def save_document(
        self,
        document_type: str,
        title: str,
        content: str,
        related_assets: list[str] | None = None,
    ) -> dict[str, Any]:
        args: dict[str, Any] = {
            "document_type": document_type,
            "title": title,
            "content": content,
        }
        if related_assets:
            args["related_assets"] = related_assets
        return self.call_tool("save_document", args)

    def add_tags(self, tag_urns: list[str], entity_urns: list[str]) -> dict[str, Any]:
        return self.call_tool("add_tags", {"tag_urns": tag_urns, "entity_urns": entity_urns})

    def close(self) -> None:
        if self._loop:
            self._loop.close()
        self._initialized = False

    @staticmethod
    def _extract_result(result: Any) -> dict[str, Any]:
        if isinstance(result, list) and result:
            item = result[0]
            if hasattr(item, "text"):
                try:
                    return json.loads(item.text)
                except (json.JSONDecodeError, TypeError):
                    return {"raw_text": item.text}
            return {"raw": str(item)}
        if isinstance(result, dict):
            return result
        return {"raw": str(result)}
