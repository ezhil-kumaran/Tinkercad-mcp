"""Configuration settings for Tinkercad MCP Server."""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

# Base project directories
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE_DIR = PROJECT_ROOT / ".tinkercad_profile"
DEFAULT_SCREENSHOTS_DIR = PROJECT_ROOT / "screenshots"

# Environment variables
PROFILE_DIR = Path(os.getenv("TINKERCAD_PROFILE_DIR", str(DEFAULT_PROFILE_DIR))).resolve()
SCREENSHOTS_DIR = Path(os.getenv("TINKERCAD_SCREENSHOTS_DIR", str(DEFAULT_SCREENSHOTS_DIR))).resolve()

# Ensure directories exist
PROFILE_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

HEADLESS_ENV = os.getenv("TINKERCAD_HEADLESS", "true").lower()
DEFAULT_HEADLESS = HEADLESS_ENV not in ("0", "false", "no", "headed")

# Security: Chromium sandbox should remain enabled by default.
# Only allow disabling sandbox if explicitly instructed via TINKERCAD_NO_SANDBOX=true (e.g. root in Docker)
NO_SANDBOX = os.getenv("TINKERCAD_NO_SANDBOX", "false").lower() in ("1", "true", "yes")

DEFAULT_TIMEOUT_MS = int(os.getenv("TINKERCAD_TIMEOUT_MS", "35000"))

# Tinkercad URLs
BASE_URL = "https://www.tinkercad.com"
LOGIN_URL = f"{BASE_URL}/login"
JOIN_URL = f"{BASE_URL}/join"
DASHBOARD_URL = f"{BASE_URL}/dashboard"
CIRCUITS_DASHBOARD_URL = f"{BASE_URL}/dashboard?type=circuits"
THINGS_CIRCUITS_URL = f"{BASE_URL}/things?type=circuits"
NEW_CIRCUIT_URL = f"{BASE_URL}/things/new?type=circuits"

# Setup logging to sys.stderr (never stdout to avoid corrupting MCP JSON-RPC messages)
logger = logging.getLogger("tinkercad_mcp")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [TinkercadMCP] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

