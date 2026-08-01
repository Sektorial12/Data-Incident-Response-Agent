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
    logger.info("DataHub Frontend URL: %s", os.getenv("DATAHUB_FRONTEND_URL", "NOT SET"))
    logger.info("MCP Mutations: %s", os.getenv("TOOLS_IS_MUTATION_ENABLED", "NOT SET"))
    logger.info("Slack Webhook: %s", "configured" if os.getenv("SLACK_WEBHOOK_URL") else "NOT SET")

    logger.info("")
    logger.info("=== Agent Pipeline ===")
    logger.info("  DataHub Actions Plugin -> Coordinator -> Tracer -> Checker -> Notifier -> Reporter")
    logger.info("")
    logger.info("To start the DataHub Actions listener:")
    logger.info("  datahub actions -c config/actions_config.yaml")
    logger.info("")
    logger.info("To test the pipeline manually:")
    logger.info("  python -m pytest tests/ -v")
    logger.info("")
    logger.info("Configuration files:")
    logger.info("  config/actions_config.yaml  — DataHub Actions plugin config")
    logger.info("  config/agent_config.yaml    — Agent settings (hops, thresholds, timeouts)")
    logger.info("  config/datahub_config.yaml  — DataHub connection settings")
    logger.info("")
    logger.info("Waiting for assertion failure events... (Ctrl+C to stop)")


if __name__ == "__main__":
    main()
