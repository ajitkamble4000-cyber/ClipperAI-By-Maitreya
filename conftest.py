"""Root pytest config: load .env for integration tests."""

from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # pragma: no cover
    load_dotenv = None

if load_dotenv and Path(".env").exists():
    load_dotenv(".env")
