"""Tests for the build command."""

import gzip
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from ccx.commands.build import (
    download_scryfall_data,
    merge_dfc_oracle_text,
    trim_and_dedupe_cards,
    write_manifest,
    write_output_files,
)


@pytest.fixture
def mock_bulk_data_response() -> dict[str, Any]:
    """Mock response from Scryfall bulk data API."""
    return {
        "data": [
            {
                "type": "oracle_cards",
                "download_uri": "https://example.com/oracle_cards.json",
            }
        ]
    }


@pytest.fixture
def sample_cards() -> list[dict[str, Any]]:
    """Sample card data for testing."""
    return [
        {
            "oracle_id": "id1",
            "name": "Lightning Bolt",
            "mana_cost": "{R}",
            "cmc": 1.0,
            "type_line": "Instant",
            "oracle_text": "Deal 3 damage to any target.",
            "colors": ["R"],
            "color_identity": ["R"],
            "keywords": [],
            "legalities": {"standard": "not_legal"},
            "reserved": False,
            "set": "lea",
            "set_name": "Limited Edition Alpha",
            "rarity": "common",
        },
        {
            "oracle_id": "id2",
            "name": "Black Lotus",
            "mana_cost": "{0}",
            "cmc": 0.0,
            "type_line": "Artifact",
            "oracle_text": (
                "{T}, Sacrifice Black Lotus: Add three mana of any one color."
            ),
            "colors": [],
            "color_identity": [],
            "keywords": [],
            "legalities": {"vintage": "restricted"},
            "reserved": True,
            "set": "lea",
            "set_name": "Limited Edition Alpha",
            "rarity": "rare",
        },
    ]


@pytest.fixture
def sample_dfc_cards() -> list[dict[str, Any]]:
    """Sample double-faced cards for testing."""
    return [
        {
            "oracle_id": "dfc1",
            "name": "Delver of Secrets // Insectile Aberration",
            "card_faces": [
                {
                    "name": "Delver of Secrets",
                    "oracle_text": (
                        "At the beginning of your upkeep, "
                        "look at the top card of your library."
                    ),
                },
                {
                    "name": "Insectile Aberration",
                    "oracle_text": "Flying",
                },
            ],
        }
    ]


def test_download_scryfall_data(
    mocker: Any,
    mock_bulk_data_response: dict[str, Any],
    sample_cards: list[dict[str, Any]],
) -> None:
    """Test downloading Scryfall data."""
    mock_get = mocker.patch("requests.get")

    # Mock the bulk data list response
    bulk_response = mocker.Mock()
    bulk_response.json.return_value = mock_bulk_data_response

    # Mock the oracle cards download response
    cards_response = mocker.Mock()
    cards_response.json.return_value = sample_cards

    # Set side effect to return different responses based on URL
    mock_get.side_effect = [bulk_response, cards_response]

    cards = download_scryfall_data()

    assert len(cards) == 2
    assert cards[0]["name"] == "Lightning Bolt"
    assert cards[1]["name"] == "Black Lotus"


def test_merge_dfc_oracle_text(sample_dfc_cards: list[dict[str, Any]]) -> None:
    """Test merging DFC oracle text."""
    processed = merge_dfc_oracle_text(sample_dfc_cards)

    assert len(processed) == 1
    assert (
        processed[0]["oracle_text"] == "At the beginning of your upkeep, "
        "look at the top card of your library. // Flying"
    )


def test_trim_and_dedupe_cards(sample_cards: list[dict[str, Any]]) -> None:
    """Test trimming and deduplication."""
    # Add a duplicate card
    duplicate_cards = sample_cards + [sample_cards[0].copy()]

    trimmed = trim_and_dedupe_cards(duplicate_cards)

    # Should deduplicate to 2 cards
    assert len(trimmed) == 2

    # Check that key fields are present
    assert "oracle_id" in trimmed[0]
    assert "name" in trimmed[0]
    assert "oracle_text" in trimmed[0]


def test_write_output_files_single_file(
    sample_cards: list[dict[str, Any]], tmp_path: Path
) -> None:
    """Test writing output when file is small."""
    files = write_output_files(sample_cards, tmp_path)

    assert len(files) == 1
    assert files[0] == "scryfall_oracle_trimmed.csv.gz"

    # Verify the file was created and can be read
    output_file = tmp_path / "scryfall_oracle_trimmed.csv.gz"
    assert output_file.exists()

    with gzip.open(output_file, "rt", encoding="utf-8") as f:
        df = pd.read_csv(f)

    assert len(df) == 2
    assert "name" in df.columns


def test_write_output_files_split(tmp_path: Path) -> None:
    """Test writing output when file needs to be split."""
    # Create a large dataset to force splitting
    large_cards = []
    for i in range(1000):
        card = {
            "oracle_id": f"id{i}",
            "name": f"{'abcdefghijklmnopqrstuvwxyz'[i % 26]}_Card_{i}",
            "mana_cost": "{1}{U}",
            "cmc": 2.0,
            "type_line": "Creature",
            "oracle_text": "A" * 500,  # Add long text to increase file size
            "colors": ["U"],
            "color_identity": ["U"],
            "keywords": [],
            "legalities": {"standard": "legal"},
            "reserved": False,
            "set": "test",
            "set_name": "Test Set",
            "rarity": "common",
        }
        large_cards.append(card)

    files = write_output_files(large_cards, tmp_path)

    # Check if files were created
    assert len(files) > 0
    for filename in files:
        file_path = tmp_path / filename
        assert file_path.exists()


def test_write_manifest(tmp_path: Path) -> None:
    """Test writing manifest file."""
    files = ["file1.csv.gz", "file2.csv.gz"]
    write_manifest(files, tmp_path)

    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.exists()

    with manifest_path.open() as f:
        manifest = json.load(f)

    assert manifest["total_files"] == 2
    assert manifest["files"] == files
    assert "build_date" in manifest
