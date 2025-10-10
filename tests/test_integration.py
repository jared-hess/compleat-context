"""Integration tests for the full build workflow."""

import json
from unittest.mock import Mock


def test_full_build_workflow_integration(mocker, tmp_path):  # type: ignore
    """Test the complete build workflow from download to output."""
    # Mock tiktoken to avoid network calls
    mock_encoding = Mock()
    mock_encoding.encode.side_effect = lambda text: [0] * (len(text) // 4 + 1)
    mocker.patch("tiktoken.get_encoding", return_value=mock_encoding)

    # Mock Scryfall API responses
    mock_bulk_response_oracle = {
        "data": [
            {
                "type": "oracle_cards",
                "download_uri": "https://example.com/oracle.json",
            },
            {
                "type": "default_cards",
                "download_uri": "https://example.com/default.json",
            },
        ]
    }

    mock_bulk_response_default = {
        "data": [
            {
                "type": "oracle_cards",
                "download_uri": "https://example.com/oracle.json",
            },
            {
                "type": "default_cards",
                "download_uri": "https://example.com/default.json",
            },
        ]
    }

    sample_oracle_cards = [
        {
            "oracle_id": "abc123",
            "name": "Test Card A",
            "mana_cost": "{1}{R}",
            "cmc": 2.0,
            "type_line": "Creature — Dragon",
            "oracle_text": "Flying",
            "colors": ["R"],
            "color_identity": ["R"],
            "keywords": ["Flying"],
            "legalities": {"standard": "legal"},
            "reserved": False,
            "set": "tst",
            "set_name": "Test Set",
            "rarity": "rare",
        },
        {
            "oracle_id": "def456",
            "name": "Test Card B",
            "card_faces": [
                {
                    "name": "Front Face",
                    "oracle_text": "Transform at the beginning of your upkeep.",
                },
                {
                    "name": "Back Face",
                    "oracle_text": "This creature has hexproof.",
                },
            ],
            "type_line": "Creature // Creature",
            "colors": ["G"],
            "color_identity": ["G"],
            "keywords": [],
            "legalities": {"standard": "legal"},
            "reserved": False,
            "set": "tst",
            "set_name": "Test Set",
            "rarity": "uncommon",
        },
    ]

    sample_default_cards = [
        {
            "oracle_id": "abc123",
            "name": "Test Card A",
            "set": "tst",
            "collector_number": "1",
            "prices": {
                "usd": "5.00",
                "usd_foil": "10.00",
            },
        },
        {
            "oracle_id": "def456",
            "name": "Test Card B",
            "set": "tst",
            "collector_number": "2",
            "prices": {
                "usd": "2.50",
            },
        },
    ]

    mock_get = mocker.patch("requests.get")

    # First call: bulk data list for oracle_cards
    bulk_response_oracle = Mock()
    bulk_response_oracle.json.return_value = mock_bulk_response_oracle

    # Second call: download oracle_cards
    cards_response_oracle = Mock()
    cards_response_oracle.json.return_value = sample_oracle_cards

    # Third call: bulk data list for default_cards
    bulk_response_default = Mock()
    bulk_response_default.json.return_value = mock_bulk_response_default

    # Fourth call: download default_cards
    cards_response_default = Mock()
    cards_response_default.json.return_value = sample_default_cards

    mock_get.side_effect = [
        bulk_response_oracle,
        cards_response_oracle,
        bulk_response_default,
        cards_response_default,
    ]

    # Import and run build command
    from ccx.commands import build

    # Patch DATA_DIR to use tmp_path
    mocker.patch.object(build, "DATA_DIR", tmp_path)

    # Run the build
    build.build()

    # Verify output files
    csv_file = tmp_path / "scryfall_oracle_trimmed.csv.gz"
    jsonl_file = tmp_path / "jsonl" / "scryfall_oracle_trimmed.jsonl.gz"
    md_file = tmp_path / "markdown" / "scryfall_oracle_trimmed.md.gz"
    manifest_file = tmp_path / "manifest.json"

    assert csv_file.exists(), "Output CSV.GZ file should exist"
    assert jsonl_file.exists(), "Output JSONL.GZ file should exist"
    assert md_file.exists(), "Output MD.GZ file should exist"
    assert manifest_file.exists(), "Manifest file should exist"

    # Verify manifest content
    with manifest_file.open() as f:
        manifest = json.load(f)

    assert "build_date" in manifest
    assert "files" in manifest
    assert "total_files" in manifest
    assert manifest["total_files"] == 3  # CSV, JSONL, MD


def test_cli_help_command(mocker):  # type: ignore
    """Test that the CLI help command works."""
    from click.testing import CliRunner

    from ccx.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "MTG rules + deckbuilding GPT CLI" in result.output


def test_cli_build_help_command(mocker):  # type: ignore
    """Test that the build command help works."""
    from click.testing import CliRunner

    from ccx.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["build", "--help"])

    assert result.exit_code == 0
    assert "Download and process Scryfall oracle cards data" in result.output
