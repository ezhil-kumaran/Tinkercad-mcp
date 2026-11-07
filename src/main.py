"""Main entry point for running the Tinkercad MCP Server over stdio."""

from __future__ import annotations

import os
import sys
from pathlib import Path
_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

os.environ.setdefault("SystemRoot", r"C:\Windows")
os.environ.setdefault("WINDIR", r"C:\Windows")
if "PATH" not in os.environ or "system32" not in os.environ["PATH"].lower():
    os.environ["PATH"] = r"C:\Windows\system32;C:\Windows;" + os.environ.get("PATH", "")

import atexit
import asyncio
try:
    from .server import server, browser
    from .config import logger
except (ImportError, ValueError):
    from src.server import server, browser
    from src.config import logger


async def _run_server_and_cleanup() -> None:
    """Run the MCP stdio server and ensure browser is cleaned up on the same event loop."""
    try:
        await server.run_stdio_async()
    finally:
        try:
            if browser.context is not None or browser.playwright is not None:
                logger.info("Cleaning up persistent browser session...")
                await browser.close()
        except Exception as e:
            logger.debug(f"Harmless error during browser shutdown: {e}")


def _cleanup_browser_sync() -> None:
    """Fallback synchronous cleanup on process termination if loop was already closed."""
    try:
        if browser.context is not None or browser.playwright is not None:
            # Check if there is an active running loop
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.create_task(browser.close())
                    return
            except RuntimeError:
                pass
            asyncio.run(browser.close())
    except Exception:
        pass


atexit.register(_cleanup_browser_sync)


def main() -> None:
    """Run the MCP server on stdio transport."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    logger.info("Starting Tinkercad Circuits MCP Server on stdio...")
    try:
        asyncio.run(_run_server_and_cleanup())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Tinkercad Circuits MCP Server stopped.")
    except Exception as e:
        logger.critical(f"Server encountered fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
