"""Data Incident Response Agent - Main Entry Point.

Starts the DataHub Actions listener which listens for assertion failure
events on Kafka and dispatches them through the agent pipeline.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _check_env() -> list[str]:
    """Validate required environment variables. Returns list of missing names."""
    required = ["DATAHUB_SERVER_URL", "DATAHUB_ACCESS_TOKEN"]
    missing = [k for k in required if not os.getenv(k)]
    return missing


def main() -> None:
    logger.info("Data Incident Response Agent starting...")
    logger.info("DataHub GMS URL: %s", os.getenv("DATAHUB_SERVER_URL", "NOT SET"))
    logger.info(
        "DataHub Frontend URL: %s", os.getenv("DATAHUB_FRONTEND_URL", "NOT SET")
    )
    logger.info("MCP Mutations: %s", os.getenv("TOOLS_IS_MUTATION_ENABLED", "NOT SET"))
    logger.info(
        "Slack Webhook: %s",
        "configured" if os.getenv("SLACK_WEBHOOK_URL") else "NOT SET",
    )

    llm_keys = {
        "Anthropic": os.getenv("ANTHROPIC_API_KEY"),
        "OpenAI": os.getenv("OPENAI_API_KEY"),
        "Google": os.getenv("GOOGLE_API_KEY"),
    }
    active_llm = next((k for k, v in llm_keys.items() if v), None)
    logger.info("LLM Provider: %s", active_llm or "none (heuristic-only mode)")

    missing = _check_env()
    if missing:
        logger.error(
            "Missing required environment variables: %s. "
            "Copy .env.example to .env and fill in values.",
            ", ".join(missing),
        )
        sys.exit(1)

    config_path = Path(__file__).parent.parent / "config" / "actions_config.yaml"
    if not config_path.exists():
        logger.error("Actions config not found: %s", config_path)
        sys.exit(1)

    logger.info("")
    logger.info("=== Agent Pipeline ===")
    logger.info(
        "  DataHub Actions (Kafka) -> Coordinator -> Tracer -> Checker -> Notifier -> Reporter"
    )
    logger.info("")
    logger.info("Starting DataHub Actions listener with config: %s", config_path)
    logger.info("Waiting for assertion failure events... (Ctrl+C to stop)")
    logger.info("")

    try:
        subprocess.run(
            ["datahub", "actions", "-c", str(config_path)],
            check=True,
        )
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except FileNotFoundError:
        logger.error(
            "datahub CLI not found. Install with: pip install acryl-datahub"
        )
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        logger.error("DataHub Actions listener exited with error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
