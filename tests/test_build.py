"""Tests for the build command."""

import gzip
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from ccx.commands.build import (
    build_legal_summary,
    colors_str,
    download_scryfall_data,
    merge_dfc_oracle_text,
    to_json,
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


def test_to_json() -> None:
    """Test JSON serialization helper."""
    # Test list
    assert to_json(["R", "G"]) == '["R","G"]'

    # Test dict
    assert to_json({"standard": "legal"}) == '{"standard":"legal"}'

    # Test empty list
    assert to_json([]) == "[]"

    # Test empty dict
    assert to_json({}) == "{}"

    # Test None becomes empty list (legacy behavior)
    assert to_json(None) == "[]"

    # Test unicode preservation
    assert to_json(["•"]) == '["•"]'


def test_colors_str() -> None:
    """Test WUBRG color string generation."""
    # Test single color
    assert colors_str(["R"]) == "R"

    # Test multiple colors in WUBRG order
    assert colors_str(["G", "R"]) == "RG"
    assert colors_str(["R", "G"]) == "RG"  # Order shouldn't matter

    # Test all colors
    assert colors_str(["W", "U", "B", "R", "G"]) == "WUBRG"

    # Test empty list
    assert colors_str([]) == ""

    # Test None
    assert colors_str(None) == ""

    # Test colorless (empty)
    assert colors_str([]) == ""


def test_build_legal_summary() -> None:
    """Test legal summary generation."""
    # Test legal only
    leg = {"standard": "legal", "modern": "legal"}
    assert build_legal_summary(leg) == "Legal: modern, standard"

    # Test not_legal only
    leg = {"standard": "not_legal"}
    assert build_legal_summary(leg) == "Not legal: standard"

    # Test banned only
    leg = {"vintage": "banned"}
    assert build_legal_summary(leg) == "Banned: vintage"

    # Test mixed
    leg = {
        "standard": "legal",
        "modern": "legal",
        "pauper": "not_legal",
        "vintage": "banned",
    }
    expected = "Legal: modern, standard • Not legal: pauper • Banned: vintage"
    assert build_legal_summary(leg) == expected

    # Test empty
    assert build_legal_summary({}) == ""


def test_trim_and_dedupe_cards_with_json_fields(
    sample_cards: list[dict[str, Any]],
) -> None:
    """Test trimming with JSON and flat field conversion."""
    trimmed = trim_and_dedupe_cards(sample_cards)

    # Check first card
    card = trimmed[0]

    # Verify JSON fields are valid JSON
    colors_parsed = json.loads(card["colors"])
    assert colors_parsed == ["R"]

    color_identity_parsed = json.loads(card["color_identity"])
    assert color_identity_parsed == ["R"]

    keywords_parsed = json.loads(card["keywords"])
    assert keywords_parsed == []

    legalities_parsed = json.loads(card["legalities"])
    assert legalities_parsed == {"standard": "not_legal"}

    # Verify flat fields
    assert card["colors_str"] == "R"
    assert card["color_identity_str"] == "R"
    assert card["keywords_joined"] == ""
    assert card["legal_standard"] == "not_legal"
    assert card["legal_summary"] == "Not legal: standard"

    # Check second card (Black Lotus - colorless)
    card2 = trimmed[1]
    assert card2["colors_str"] == ""
    assert card2["color_identity_str"] == ""
    assert card2["legal_vintage"] == "restricted"


def test_keywords_joined() -> None:
    """Test keywords_joined field."""
    cards = [
        {
            "oracle_id": "test1",
            "name": "Test Card",
            "keywords": ["Haste", "Partner"],
        }
    ]

    trimmed = trim_and_dedupe_cards(cards)
    assert trimmed[0]["keywords_joined"] == "Haste; Partner"


def test_csv_with_embedded_newlines(tmp_path: Path) -> None:
    """Test CSV round-trip with embedded newlines in oracle_text."""
    cards = [
        {
            "oracle_id": "test1",
            "name": "Test Card",
            "oracle_text": "First line\nSecond line\nThird line",
            "colors": ["U"],
            "color_identity": ["U"],
            "keywords": [],
            "legalities": {"standard": "legal"},
        }
    ]

    trimmed = trim_and_dedupe_cards(cards)
    files = write_output_files(trimmed, tmp_path)

    # Read back the CSV
    output_file = tmp_path / files[0]
    with gzip.open(output_file, "rt", encoding="utf-8") as f:
        df = pd.read_csv(f)

    # Verify oracle_text preserved newlines
    assert df.iloc[0]["oracle_text"] == "First line\nSecond line\nThird line"


def test_multicolor_wubrg_order() -> None:
    """Test WUBRG ordering for multicolor cards."""
    cards = [
        {
            "oracle_id": "test1",
            "name": "Niv-Mizzet",
            "colors": ["U", "R"],  # Input order
            "color_identity": ["R", "U"],  # Different input order
            "keywords": [],
            "legalities": {},
        }
    ]

    trimmed = trim_and_dedupe_cards(cards)
    # Both should output as "UR" regardless of input order
    assert trimmed[0]["colors_str"] == "UR"
    assert trimmed[0]["color_identity_str"] == "UR"
