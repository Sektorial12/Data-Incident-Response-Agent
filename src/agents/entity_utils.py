"""Shared utilities for entity metadata extraction.

Used by Tracer and Checker agents to parse get_entities responses
in both MCP server format (list of dicts) and legacy format (dict with
"entities" key containing aspect-based data).
"""

import time
from typing import Any


def extract_entity_info(
    entities_result: dict[str, Any] | list[Any], urn: str
) -> dict[str, Any]:
    """Extract relevant info from a get_entities response.

    Returns a dict with optional keys:
    - name: str
    - platform: str
    - has_failed_assertions: bool
    - recently_modified: bool
    - recently_created: bool
    - freshness_stale: bool
    - missing_lineage: bool
    - tags: list[str]
    - owners: list[str]

    Handles MCP server format (list of entity dicts with direct fields)
    and legacy format (dict with "entities" key containing aspect-based data).
    """
    info: dict[str, Any] = {}

    if isinstance(entities_result, list):
        _extract_from_mcp_format(entities_result, urn, info)
        return info

    if isinstance(entities_result, dict):
        entities = entities_result.get("entities", [])
        for entity in entities:
            if isinstance(entity, dict) and entity.get("urn") == urn:
                info["name"] = entity.get("name") or entity.get("qualifiedName")
                info["platform"] = entity.get("platform")
                aspects = entity.get("aspects", [])
                aspect_names = set()
                for aspect in aspects:
                    if isinstance(aspect, dict):
                        aspect_name = aspect.get("name", "")
                        aspect_names.add(aspect_name)
                        if aspect_name == "assertionRunEvents":
                            info["has_failed_assertions"] = True
                        if aspect_name == "schemaMetadata":
                            info["recently_modified"] = True
                        if aspect_name == "datasetProperties":
                            info["freshness_stale"] = False
                        if aspect_name == "dataPlatformInfo":
                            created = aspect.get("created", {})
                            if isinstance(created, dict):
                                created_time = created.get("time")
                                if created_time:
                                    age_seconds = (time.time() * 1000 - created_time) / 1000
                                    if age_seconds < 86400 * 7:
                                        info["recently_created"] = True
                if "upstreamLineage" not in aspect_names:
                    info["missing_lineage"] = True
                break

    return info


def _extract_from_mcp_format(
    entities: list[Any], urn: str, info: dict[str, Any]
) -> None:
    """Extract entity info from MCP server format (list of entity dicts)."""
    for entity in entities:
        if isinstance(entity, dict) and entity.get("urn") == urn:
            info["name"] = entity.get("name") or entity.get("qualifiedName", "")
            platform = entity.get("platform")
            if isinstance(platform, dict):
                info["platform"] = platform.get("name", "")
            else:
                info["platform"] = platform

            health = entity.get("health")
            if isinstance(health, dict):
                status = health.get("status", "")
                if status.upper() in ("FAIL", "FAILED", "ERROR"):
                    info["has_failed_assertions"] = True

            schema = entity.get("schemaMetadata")
            if isinstance(schema, dict):
                info["recently_modified"] = True
                created_time = schema.get("createdAt")
                if created_time:
                    age_seconds = (time.time() * 1000 - created_time) / 1000
                    if age_seconds < 86400 * 7:
                        info["recently_created"] = True

            properties = entity.get("properties", {})
            if isinstance(properties, dict) and properties:
                info["freshness_stale"] = False

            tags = entity.get("tags", {})
            if isinstance(tags, dict):
                tag_list = tags.get("tags", [])
                info["tags"] = [
                    t.get("tag", {}).get("urn", "")
                    for t in tag_list
                    if isinstance(t, dict)
                ]

            ownership = entity.get("ownership", {})
            if isinstance(ownership, dict):
                owners = ownership.get("owners", [])
                info["owners"] = [
                    o.get("owner", {}).get("urn", "")
                    for o in owners
                    if isinstance(o, dict)
                ]

            break


def extract_dataset_name(urn: str) -> str:
    """Extract a human-readable name from a dataset URN.

    Handles common URN formats:
    - urn:li:dataset:(urn:li:dataPlatform:sqlite,healthcare.main.mart_billing,PROD)
    -> healthcare.main.mart_billing
    - urn:li:dataset:(urn:li:dataPlatform:snowflake,mydb.schema.table,PROD)
    -> mydb.schema.table
    """
    if "sqlite," in urn:
        parts = urn.split("sqlite,")
        if len(parts) > 1:
            rest = parts[1].rstrip(")")
            return rest.split(",")[0] if "," in rest else rest
    return urn
