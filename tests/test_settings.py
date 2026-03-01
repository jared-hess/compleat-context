"""Tests for settings module."""

import os
from pathlib import Path
from unittest.mock import patch


def test_default_settings() -> None:
    """Test that default settings are loaded correctly."""
    # Import after clearing env to get defaults
    with patch.dict(os.environ, {}, clear=True):
        # Force reload of settings module to pick up cleared environment
        import importlib

        from ccx import settings

        importlib.reload(settings)

        # Test Scryfall settings
        assert settings.SCRYFALL_BULK_DATA_URL == "https://api.scryfall.com/bulk-data"
        assert settings.ORACLE_CARDS_TYPE == "oracle_cards"
        assert settings.DEFAULT_CARDS_TYPE == "default_cards"

        # Test Spellbook settings
        assert (
            settings.SPELLBOOK_URL
            == "https://json.commanderspellbook.com/variants.json"
        )

        # Test data directories
        assert settings.DATA_DIR == Path("data")
        assert settings.SPELLBOOK_DATA_DIR == Path("data/spellbook")

        # Test file size and token limits
        assert settings.MAX_FILE_SIZE_MB == 50
        assert settings.MAX_FILE_SIZE_BYTES == 512 * 1024 * 1024
        assert settings.MAX_TOKENS_PER_FILE == 2_000_000

        # Test MTG constants
        assert settings.WUBRG == ["W", "U", "B", "R", "G"]


def test_env_override_string_settings() -> None:
    """Test that environment variables override default string settings."""
    env_vars = {
        "SCRYFALL_BULK_DATA_URL": "https://custom.scryfall.com/api",
        "ORACLE_CARDS_TYPE": "custom_oracle",
        "DEFAULT_CARDS_TYPE": "custom_default",
        "SPELLBOOK_URL": "https://custom.spellbook.com/api",
    }

    with patch.dict(os.environ, env_vars, clear=True):
        import importlib

        from ccx import settings

        importlib.reload(settings)

        assert settings.SCRYFALL_BULK_DATA_URL == "https://custom.scryfall.com/api"
        assert settings.ORACLE_CARDS_TYPE == "custom_oracle"
        assert settings.DEFAULT_CARDS_TYPE == "custom_default"
        assert settings.SPELLBOOK_URL == "https://custom.spellbook.com/api"


def test_env_override_path_settings() -> None:
    """Test that environment variables override default path settings."""
    env_vars = {
        "DATA_DIR": "/tmp/custom_data",
        "SPELLBOOK_DATA_DIR": "/tmp/spellbook",
    }

    with patch.dict(os.environ, env_vars, clear=True):
        import importlib

        from ccx import settings

        importlib.reload(settings)

        assert settings.DATA_DIR == Path("/tmp/custom_data")
        assert settings.SPELLBOOK_DATA_DIR == Path("/tmp/spellbook")


def test_env_override_int_settings() -> None:
    """Test that environment variables override default integer settings."""
    env_vars = {
        "MAX_FILE_SIZE_MB": "100",
        "MAX_FILE_SIZE_BYTES": "1073741824",  # 1GB
        "MAX_TOKENS_PER_FILE": "5000000",
    }

    with patch.dict(os.environ, env_vars, clear=True):
        import importlib

        from ccx import settings

        importlib.reload(settings)

        assert settings.MAX_FILE_SIZE_MB == 100
        assert settings.MAX_FILE_SIZE_BYTES == 1073741824
        assert settings.MAX_TOKENS_PER_FILE == 5000000


def test_env_invalid_int_falls_back_to_default() -> None:
    """Test that invalid integer values fall back to defaults."""
    env_vars = {
        "MAX_FILE_SIZE_MB": "not_a_number",
        "MAX_TOKENS_PER_FILE": "also_invalid",
    }

    with patch.dict(os.environ, env_vars, clear=True):
        import importlib

        from ccx import settings

        importlib.reload(settings)

        # Should fall back to defaults
        assert settings.MAX_FILE_SIZE_MB == 50
        assert settings.MAX_TOKENS_PER_FILE == 2_000_000


def test_wubrg_constant_not_overridable() -> None:
    """Test that WUBRG constant is always the same."""
    # WUBRG is a list constant, not configurable via env
    from ccx import settings

    assert settings.WUBRG == ["W", "U", "B", "R", "G"]
    assert isinstance(settings.WUBRG, list)
