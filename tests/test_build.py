"""Tests for the build command."""

import gzip
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from ccx.commands.build import (
    _best_price_from_printing,
    build_legal_summary,
    build_oracle_price_index,
    colors_str,
    download_scryfall_data,
    filter_playable_cards,
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


def test_filter_playable_cards_removes_art_series() -> None:
    """Test filtering removes art series cards."""
    cards = [
        {
            "oracle_id": "art1",
            "name": "Art Card",
            "layout": "art_series",
            "oracle_text": "",
            "type_line": "",
        },
        {
            "oracle_id": "real1",
            "name": "Real Card",
            "layout": "normal",
            "oracle_text": "Draw a card.",
            "type_line": "Instant",
        },
    ]

    filtered = filter_playable_cards(cards)
    assert len(filtered) == 1
    assert filtered[0]["oracle_id"] == "real1"


def test_filter_playable_cards_removes_tokens() -> None:
    """Test filtering removes token cards."""
    cards = [
        {
            "oracle_id": "token1",
            "name": "Goblin Token",
            "layout": "token",
            "oracle_text": "",
            "type_line": "Token Creature — Goblin",
        },
        {
            "oracle_id": "token2",
            "name": "Day // Night",
            "layout": "double_faced_token",
            "oracle_text": "",
            "type_line": "",
        },
        {
            "oracle_id": "real1",
            "name": "Lightning Bolt",
            "layout": "normal",
            "oracle_text": "Deal 3 damage.",
            "type_line": "Instant",
        },
    ]

    filtered = filter_playable_cards(cards)
    assert len(filtered) == 1
    assert filtered[0]["oracle_id"] == "real1"


def test_filter_playable_cards_removes_emblems() -> None:
    """Test filtering removes emblem cards."""
    cards = [
        {
            "oracle_id": "emblem1",
            "name": "Chandra Emblem",
            "layout": "emblem",
            "oracle_text": "You get an emblem.",
            "type_line": "Emblem",
        },
        {
            "oracle_id": "real1",
            "name": "Chandra, Torch of Defiance",
            "layout": "normal",
            "oracle_text": "+1: Add {R}{R}.",
            "type_line": "Legendary Planeswalker — Chandra",
        },
    ]

    filtered = filter_playable_cards(cards)
    assert len(filtered) == 1
    assert filtered[0]["oracle_id"] == "real1"


def test_filter_playable_cards_removes_memorabilia() -> None:
    """Test filtering removes memorabilia set type."""
    cards = [
        {
            "oracle_id": "memo1",
            "name": "Memorabilia Card",
            "layout": "normal",
            "set_type": "memorabilia",
            "oracle_text": "Some text.",
            "type_line": "Artifact",
        },
        {
            "oracle_id": "real1",
            "name": "Black Lotus",
            "layout": "normal",
            "set_type": "core",
            "oracle_text": "{T}: Add three mana.",
            "type_line": "Artifact",
        },
    ]

    filtered = filter_playable_cards(cards)
    assert len(filtered) == 1
    assert filtered[0]["oracle_id"] == "real1"


def test_filter_playable_cards_removes_art_series_by_name() -> None:
    """Test filtering removes cards with 'Art Series' in set_name."""
    cards = [
        {
            "oracle_id": "art1",
            "name": "Mountain",
            "layout": "normal",
            "set": "aznr",
            "set_name": "Zendikar Rising Art Series",
            "oracle_text": "",
            "type_line": "Basic Land — Mountain",
        },
        {
            "oracle_id": "real1",
            "name": "Mountain",
            "layout": "normal",
            "set": "znr",
            "set_name": "Zendikar Rising",
            "oracle_text": "({T}: Add {R}.)",
            "type_line": "Basic Land — Mountain",
        },
    ]

    filtered = filter_playable_cards(cards)
    assert len(filtered) == 1
    assert filtered[0]["oracle_id"] == "real1"


def test_filter_playable_cards_requires_oracle_text_or_type_line() -> None:
    """Test filtering requires oracle_text or type_line."""
    cards = [
        {
            "oracle_id": "empty1",
            "name": "Empty Card",
            "layout": "normal",
            "oracle_text": "",
            "type_line": "",
        },
        {
            "oracle_id": "has_oracle",
            "name": "Card with Oracle",
            "layout": "normal",
            "oracle_text": "Do something.",
            "type_line": "",
        },
        {
            "oracle_id": "has_type",
            "name": "Card with Type",
            "layout": "normal",
            "oracle_text": "",
            "type_line": "Artifact",
        },
        {
            "oracle_id": "has_both",
            "name": "Card with Both",
            "layout": "normal",
            "oracle_text": "Tap: Do something.",
            "type_line": "Artifact",
        },
    ]

    filtered = filter_playable_cards(cards)
    assert len(filtered) == 3
    oracle_ids = {card["oracle_id"] for card in filtered}
    assert oracle_ids == {"has_oracle", "has_type", "has_both"}


def test_filter_playable_cards_handles_missing_fields() -> None:
    """Test filtering handles cards with missing fields gracefully."""
    cards = [
        {
            "oracle_id": "minimal1",
            "name": "Minimal Card",
            # No layout field
            # No set_type field
            # No set_name field
            "oracle_text": "Some text.",
            # No type_line field
        },
        {
            "oracle_id": "minimal2",
            "name": "Another Minimal",
            # No layout, set_type, set_name, oracle_text
            "type_line": "Creature",
        },
    ]

    filtered = filter_playable_cards(cards)
    assert len(filtered) == 2
    assert filtered[0]["oracle_id"] == "minimal1"
    assert filtered[1]["oracle_id"] == "minimal2"


def test_filter_playable_cards_comprehensive() -> None:
    """Test filtering with a comprehensive mix of card types."""
    cards = [
        # Should keep: normal playable card
        {
            "oracle_id": "keep1",
            "name": "Lightning Bolt",
            "layout": "normal",
            "set_type": "expansion",
            "set_name": "Alpha",
            "oracle_text": "Deal 3 damage.",
            "type_line": "Instant",
        },
        # Should remove: art series layout
        {
            "oracle_id": "remove1",
            "name": "Art Card",
            "layout": "art_series",
            "oracle_text": "",
            "type_line": "",
        },
        # Should remove: token layout
        {
            "oracle_id": "remove2",
            "name": "Goblin Token",
            "layout": "token",
            "oracle_text": "",
            "type_line": "Token Creature",
        },
        # Should remove: emblem
        {
            "oracle_id": "remove3",
            "name": "Emblem",
            "layout": "emblem",
            "oracle_text": "Text",
            "type_line": "Emblem",
        },
        # Should remove: memorabilia set
        {
            "oracle_id": "remove4",
            "name": "Memorabilia",
            "layout": "normal",
            "set_type": "memorabilia",
            "oracle_text": "Text",
            "type_line": "Artifact",
        },
        # Should remove: Art Series in set name
        {
            "oracle_id": "remove5",
            "name": "Mountain Art",
            "layout": "normal",
            "set_name": "Zendikar Rising Art Series",
            "oracle_text": "",
            "type_line": "Land",
        },
        # Should remove: no oracle text or type line
        {
            "oracle_id": "remove6",
            "name": "Empty",
            "layout": "normal",
            "oracle_text": "",
            "type_line": "",
        },
        # Should keep: has type_line even without oracle_text
        {
            "oracle_id": "keep2",
            "name": "Basic Land",
            "layout": "normal",
            "set_type": "core",
            "set_name": "Alpha",
            "oracle_text": "",
            "type_line": "Basic Land — Forest",
        },
    ]

    filtered = filter_playable_cards(cards)
    assert len(filtered) == 2
    oracle_ids = {card["oracle_id"] for card in filtered}
    assert oracle_ids == {"keep1", "keep2"}

