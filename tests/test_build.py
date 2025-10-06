"""Tests for the build command."""

import gzip
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from ccx.commands.build import (
    _best_price_from_printing,
    build_oracle_price_index,
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


def test_best_price_from_printing() -> None:
    """Test extracting prices from a printing."""
    # Test with all price types
    prices = {"usd": "2.95", "usd_foil": "5.50", "usd_etched": "10.00"}
    result = _best_price_from_printing(prices)
    assert len(result) == 3
    assert ("nonfoil", 2.95) in result
    assert ("foil", 5.50) in result
    assert ("etched", 10.00) in result

    # Test with missing prices
    prices = {"usd": "1.00", "usd_foil": None}  # type: ignore[dict-item]
    result = _best_price_from_printing(prices)
    assert len(result) == 1
    assert result[0] == ("nonfoil", 1.00)

    # Test with invalid price strings
    prices = {"usd": "invalid", "usd_foil": "3.50"}
    result = _best_price_from_printing(prices)
    assert len(result) == 1
    assert result[0] == ("foil", 3.50)

    # Test with empty prices
    result = _best_price_from_printing({})
    assert len(result) == 0


def test_build_oracle_price_index() -> None:
    """Test building price index from default_cards."""
    default_cards = [
        {
            "oracle_id": "oracle1",
            "set": "cmr",
            "collector_number": "684",
            "prices": {"usd": "2.95", "usd_foil": "5.50"},
        },
        {
            "oracle_id": "oracle1",
            "set": "m21",
            "collector_number": "100",
            "prices": {"usd": "89.99"},
        },
        {
            "oracle_id": "oracle1",
            "set": "lea",
            "collector_number": "1",
            "prices": {"usd": "7.50"},
        },
        {
            "oracle_id": "oracle2",
            "set": "znr",
            "collector_number": "200",
            "prices": {"usd": "0.25"},
        },
        {
            "oracle_id": "oracle3",
            "set": "test",
            "collector_number": "99",
            "prices": {},  # No prices
        },
    ]

    price_index = build_oracle_price_index(default_cards)

    # oracle1 should have prices
    assert "oracle1" in price_index
    oracle1_prices = price_index["oracle1"]
    assert oracle1_prices["lowest_price_usd"] == "2.95"
    assert oracle1_prices["lowest_price_finish"] == "nonfoil"
    assert oracle1_prices["lowest_price_set"] == "cmr"
    assert oracle1_prices["lowest_price_collector"] == "684"
    assert (
        oracle1_prices["median_price_usd"] == "6.50"
    )  # median of 2.95, 5.50, 7.50, 89.99
    assert oracle1_prices["highest_price_usd"] == "89.99"
    assert "CMR #684" in oracle1_prices["price_summary"]
    assert "nonfoil" in oracle1_prices["price_summary"]
    assert "Range" in oracle1_prices["price_summary"]
    assert "median" in oracle1_prices["price_summary"]

    # oracle2 should have prices but no range (single price)
    assert "oracle2" in price_index
    oracle2_prices = price_index["oracle2"]
    assert oracle2_prices["lowest_price_usd"] == "0.25"
    assert "Range" not in oracle2_prices["price_summary"]
    assert "median" not in oracle2_prices["price_summary"]

    # oracle3 should not be in index (no valid prices)
    assert "oracle3" not in price_index


def test_build_oracle_price_index_multiple_finishes() -> None:
    """Test price index with multiple finishes for the same printing."""
    default_cards = [
        {
            "oracle_id": "oracle1",
            "set": "neo",
            "collector_number": "50",
            "prices": {"usd": "10.00", "usd_foil": "3.00", "usd_etched": "15.00"},
        },
    ]

    price_index = build_oracle_price_index(default_cards)

    assert "oracle1" in price_index
    oracle1_prices = price_index["oracle1"]
    # Cheapest should be foil at 3.00
    assert oracle1_prices["lowest_price_usd"] == "3.00"
    assert oracle1_prices["lowest_price_finish"] == "foil"
    assert oracle1_prices["highest_price_usd"] == "15.00"
    # Median of [3.00, 10.00, 15.00] is 10.00
    assert oracle1_prices["median_price_usd"] == "10.00"


def test_trim_and_dedupe_cards_with_price_index() -> None:
    """Test trimming and deduplication with price index."""
    sample_cards = [
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
            "oracle_text": "{T}, Sacrifice Black Lotus: Add three mana.",
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

    price_index = {
        "id1": {
            "lowest_price_usd": "0.50",
            "lowest_price_finish": "nonfoil",
            "lowest_price_set": "m21",
            "lowest_price_collector": "100",
            "median_price_usd": "1.00",
            "highest_price_usd": "2.00",
            "price_summary": (
                "$0.50 (cheapest: M21 #100, nonfoil). "
                "Range $0.50–$2.00. median $1.00."
            ),
        }
    }

    trimmed = trim_and_dedupe_cards(sample_cards, price_index)

    assert len(trimmed) == 2

    # Check that id1 has price data
    id1_card = next(c for c in trimmed if c["oracle_id"] == "id1")
    assert id1_card["lowest_price_usd"] == "0.50"
    assert id1_card["lowest_price_finish"] == "nonfoil"
    assert id1_card["lowest_price_set"] == "m21"
    assert id1_card["lowest_price_collector"] == "100"
    assert id1_card["median_price_usd"] == "1.00"
    assert id1_card["highest_price_usd"] == "2.00"
    assert "M21 #100" in id1_card["price_summary"]

    # Check that id2 has empty price fields (not in index)
    id2_card = next(c for c in trimmed if c["oracle_id"] == "id2")
    assert id2_card["lowest_price_usd"] == ""
    assert id2_card["lowest_price_finish"] == ""
    assert id2_card["price_summary"] == ""


def test_trim_and_dedupe_cards_without_price_index() -> None:
    """Test trimming and deduplication without price index (backward compat)."""
    sample_cards = [
        {
            "oracle_id": "id1",
            "name": "Test Card",
            "mana_cost": "{U}",
            "cmc": 1.0,
            "type_line": "Instant",
            "oracle_text": "Draw a card.",
            "colors": ["U"],
            "color_identity": ["U"],
            "keywords": [],
            "legalities": {"standard": "legal"},
            "reserved": False,
            "set": "znr",
            "set_name": "Zendikar Rising",
            "rarity": "common",
        }
    ]

    # Call without price_index
    trimmed = trim_and_dedupe_cards(sample_cards)

    assert len(trimmed) == 1
    # Price fields should not exist when no price_index is provided
    assert "lowest_price_usd" not in trimmed[0]
