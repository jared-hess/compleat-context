"""Application settings with environment variable and .env file support."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env file if it exists (won't override existing environment variables)
load_dotenv()


def _get_env_str(key: str, default: str) -> str:
    """Get string environment variable with default."""
    return os.getenv(key, default)


def _get_env_int(key: str, default: int) -> int:
    """Get integer environment variable with default."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_path(key: str, default: str) -> Path:
    """Get Path environment variable with default."""
    return Path(os.getenv(key, default))


# Scryfall API settings
SCRYFALL_BULK_DATA_URL: str = _get_env_str(
    "SCRYFALL_BULK_DATA_URL", "https://api.scryfall.com/bulk-data"
)
ORACLE_CARDS_TYPE: str = _get_env_str("ORACLE_CARDS_TYPE", "oracle_cards")
DEFAULT_CARDS_TYPE: str = _get_env_str("DEFAULT_CARDS_TYPE", "default_cards")

# Commander Spellbook API settings
SPELLBOOK_URL: str = _get_env_str(
    "SPELLBOOK_URL", "https://json.commanderspellbook.com/variants.json"
)

# Data directory settings
DATA_DIR: Path = _get_env_path("DATA_DIR", "data")
SPELLBOOK_DATA_DIR: Path = _get_env_path("SPELLBOOK_DATA_DIR", "data/spellbook")

# File size and token limits
MAX_FILE_SIZE_MB: int = _get_env_int("MAX_FILE_SIZE_MB", 50)
MAX_FILE_SIZE_BYTES: int = _get_env_int("MAX_FILE_SIZE_BYTES", 512 * 1024 * 1024)
MAX_TOKENS_PER_FILE: int = _get_env_int("MAX_TOKENS_PER_FILE", 2_000_000)

# Magic: The Gathering constants
WUBRG: list[str] = ["W", "U", "B", "R", "G"]
