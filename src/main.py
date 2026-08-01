"""Data Incident Response Agent - Main Entry Point.

Starts the DataHub Actions listener and Coordinator agent.
"""

import logging
import sys
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Data Incident Response Agent starting...")
    logger.info("DataHub GMS URL: %s", os.getenv("DATAHUB_SERVER_URL", "NOT SET"))
    logger.info("MCP Mutations: %s", os.getenv("TOOLS_IS_MUTATION_ENABLED", "NOT SET"))

    # TODO: Phase 2 - Start DataHub Actions plugin
    # TODO: Phase 3 - Initialize Coordinator agent
    # TODO: Phase 8 - Wire full pipeline

    logger.info("Agent not yet implemented. See roadmap.md for development phases.")


if __name__ == "__main__":
    main()
