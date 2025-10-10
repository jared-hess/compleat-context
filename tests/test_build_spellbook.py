"""Tests for the build_spellbook command."""

import gzip
import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from ccx.commands.build_spellbook import (
    _write_card_index,
    _write_csv_files,
    open_json_file,
    parse_spellbook_combos,
    write_jsonl_files,
    write_markdown_files,
)


@pytest.fixture(autouse=True)
def mock_tiktoken_encoding(mocker: Any) -> None:
    """Mock tiktoken encoding to avoid network calls in tests."""
    mock_encoding = Mock()
    # Simple mock: 1 token per 4 characters (approximate)
    mock_encoding.encode.side_effect = lambda text: [0] * (len(text) // 4 + 1)
    mocker.patch("tiktoken.get_encoding", return_value=mock_encoding)


@pytest.fixture
def sample_combos() -> list[dict[str, Any]]:
    """Sample combo data for testing (raw API format)."""
    return [
        {
            "id": "combo-1",
            "status": "ok",
            "identity": "WU",
            "manaNeeded": "{3}{W}{U}",
            "manaValueNeeded": 5,
            "description": "Step 1: Do thing A. Step 2: Do thing B.",
            "notes": "This combo is fragile.",
            "popularity": 100,
            "bracketTag": 3,
            "legalities": {"commander": "legal", "vintage": "legal"},
            "prices": {"usd": "50.00"},
            "variantCount": 1,
            "uses": [
                {
                    "card": {
                        "name": "Card A",
                        "oracleId": "oracle-a",
                        "typeLine": "Creature - Human Wizard",
                    }
                },
                {
                    "card": {
                        "name": "Card B",
                        "oracleId": "oracle-b",
                        "typeLine": "Artifact",
                    }
                },
            ],
            "produces": [
                {"feature": {"name": "Infinite mana"}},
                {"feature": {"name": "Infinite card draw"}},
            ],
            "requires": "Some requirement",
        },
        {
            "id": "combo-2",
            "status": "ok",
            "identity": "R",
            "manaNeeded": "{R}",
            "manaValueNeeded": 1,
            "description": "Step 1: Win the game.",
            "popularity": 200,
            "uses": [
                {
                    "card": {
                        "name": "Card C",
                        "oracleId": "oracle-c",
                        "typeLine": "Sorcery",
                    }
                },
            ],
            "produces": [
                {"feature": {"name": "You win the game"}},
            ],
        },
    ]


@pytest.fixture
def sample_variants_json(tmp_path: Path, sample_combos: list[dict[str, Any]]) -> Path:
    """Create a sample variants.json file for testing."""
    json_file = tmp_path / "variants.json"
    with open(json_file, "w") as f:
        # Wrap in the actual API structure
        json.dump({"variants": sample_combos}, f)
    return json_file


@pytest.fixture
def normalized_combos() -> list[dict[str, Any]]:
    """Sample normalized combo data (after parsing)."""
    return [
        {
            "id": "combo-1",
            "status": "ok",
            "identity": "WU",
            "manaNeeded": "{3}{W}{U}",
            "manaValueNeeded": 5,
            "description": "Step 1: Do thing A. Step 2: Do thing B.",
            "notes": "This combo is fragile.",
            "popularity": 100,
            "bracketTag": 3,
            "legalities": {"commander": "legal", "vintage": "legal"},
            "prices": {"usd": "50.00"},
            "variantCount": 1,
            "uses": [
                {
                    "name": "Card A",
                    "oracleId": "oracle-a",
                    "typeLine": "Creature - Human Wizard",
                },
                {
                    "name": "Card B",
                    "oracleId": "oracle-b",
                    "typeLine": "Artifact",
                },
            ],
            "produces": [
                {"name": "Infinite mana"},
                {"name": "Infinite card draw"},
            ],
            "requires": "Some requirement",
        },
        {
            "id": "combo-2",
            "status": "ok",
            "identity": "R",
            "manaNeeded": "{R}",
            "manaValueNeeded": 1,
            "description": "Step 1: Win the game.",
            "popularity": 200,
            "uses": [
                {
                    "name": "Card C",
                    "oracleId": "oracle-c",
                    "typeLine": "Sorcery",
                },
            ],
            "produces": [
                {"name": "You win the game"},
            ],
        },
    ]


def test_open_json_file(tmp_path: Path) -> None:
    """Test opening both .json and .json.gz files."""
    # Test .json
    json_file = tmp_path / "test.json"
    json_file.write_text('{"test": "data"}')

    with open_json_file(json_file) as f:
        data = json.load(f)
        assert data == {"test": "data"}

    # Test .json.gz
    gz_file = tmp_path / "test.json.gz"
    with gzip.open(gz_file, "wt") as f:
        json.dump({"test": "gzip"}, f)

    with open_json_file(gz_file) as f:
        data = json.load(f)
        assert data == {"test": "gzip"}


def test_parse_spellbook_combos(sample_variants_json: Path) -> None:
    """Test parsing spellbook combos with streaming."""
    combos = list(parse_spellbook_combos(sample_variants_json))

    assert len(combos) == 2

    # Check first combo
    combo1 = combos[0]
    assert combo1["id"] == "combo-1"
    assert combo1["identity"] == "WU"
    assert combo1["manaNeeded"] == "{3}{W}{U}"
    assert combo1["popularity"] == 100
    assert len(combo1["uses"]) == 2
    assert combo1["uses"][0]["name"] == "Card A"
    assert combo1["uses"][0]["oracleId"] == "oracle-a"
    assert len(combo1["produces"]) == 2
    assert combo1["produces"][0]["name"] == "Infinite mana"
    assert "requires" in combo1

    # Check second combo
    combo2 = combos[1]
    assert combo2["id"] == "combo-2"
    assert len(combo2["uses"]) == 1
    assert len(combo2["produces"]) == 1


def test_parse_spellbook_combos_filters_fields(sample_variants_json: Path) -> None:
    """Test that parsing only keeps specified fields."""
    combos = list(parse_spellbook_combos(sample_variants_json))

    # Check that we kept the right fields
    combo = combos[0]
    assert "id" in combo
    assert "identity" in combo
    assert "uses" in combo
    assert "produces" in combo

    # Check uses format
    assert isinstance(combo["uses"], list)
    for card in combo["uses"]:
        assert "name" in card or "oracleId" in card or "typeLine" in card
        # Should NOT have full card object
        assert set(card.keys()).issubset({"name", "oracleId", "typeLine"})

    # Check produces format
    assert isinstance(combo["produces"], list)
    for feature in combo["produces"]:
        assert "name" in feature
        assert set(feature.keys()) == {"name"}


def test_write_jsonl_files(
    normalized_combos: list[dict[str, Any]], tmp_path: Path
) -> None:
    """Test writing combos to JSONL."""
    files = write_jsonl_files(normalized_combos, tmp_path, compress=False)

    assert len(files) == 1
    assert files[0] == "combos.jsonl"

    # Verify file contents
    jsonl_file = tmp_path / "combos.jsonl"
    assert jsonl_file.exists()

    with open(jsonl_file) as f:
        lines = f.readlines()

    assert len(lines) == 2

    # Parse and verify
    combo1 = json.loads(lines[0])
    assert combo1["id"] == "combo-1"

    combo2 = json.loads(lines[1])
    assert combo2["id"] == "combo-2"


def test_write_jsonl_files_compressed(
    normalized_combos: list[dict[str, Any]], tmp_path: Path
) -> None:
    """Test writing compressed JSONL."""
    files = write_jsonl_files(normalized_combos, tmp_path, compress=True)

    assert len(files) == 1
    assert files[0] == "combos.jsonl.gz"

    # Verify file contents
    jsonl_file = tmp_path / "combos.jsonl.gz"
    assert jsonl_file.exists()

    with gzip.open(jsonl_file, "rt") as f:
        lines = f.readlines()

    assert len(lines) == 2


def test__write_csv_files(
    normalized_combos: list[dict[str, Any]], tmp_path: Path
) -> None:
    """Test writing combos to CSV."""
    files = _write_csv_files(normalized_combos, tmp_path, compress=False)

    assert len(files) == 1
    assert files[0] == "combos.csv"

    csv_file = tmp_path / "combos.csv"
    assert csv_file.exists()

    # Read and verify
    import pandas as pd

    df = pd.read_csv(csv_file)

    assert len(df) == 2
    assert "id" in df.columns
    assert "identity" in df.columns
    assert "features" in df.columns
    assert "card1" in df.columns
    assert "card2" in df.columns
    assert "card3" in df.columns
    assert "card_count" in df.columns

    # Check first row
    row1 = df.iloc[0]
    assert row1["id"] == "combo-1"
    assert row1["identity"] == "WU"
    assert "Infinite mana" in row1["features"]
    assert row1["card1"] == "Card A"
    assert row1["card2"] == "Card B"
    assert row1["card_count"] == 2

    # Check second row
    row2 = df.iloc[1]
    assert row2["id"] == "combo-2"
    assert row2["card1"] == "Card C"
    assert row2["card_count"] == 1


def test__write_card_index(
    normalized_combos: list[dict[str, Any]], tmp_path: Path
) -> None:
    """Test writing combo card index."""
    files = _write_card_index(normalized_combos, tmp_path, compress=False)

    assert len(files) == 1
    assert files[0] == "combo_card_index.jsonl"

    index_file = tmp_path / "combo_card_index.jsonl"
    assert index_file.exists()

    # Read and verify
    with open(index_file) as f:
        lines = f.readlines()

    # Should have 3 unique oracle IDs
    assert len(lines) == 3

    # Parse entries
    entries = [json.loads(line) for line in lines]

    # Find entry for oracle-a
    oracle_a = next(e for e in entries if e["oracleId"] == "oracle-a")
    assert oracle_a["name"] == "Card A"
    assert "combo-1" in oracle_a["combo_ids"]

    # Find entry for oracle-c
    oracle_c = next(e for e in entries if e["oracleId"] == "oracle-c")
    assert oracle_c["name"] == "Card C"
    assert "combo-2" in oracle_c["combo_ids"]


def test_write_markdown_files(
    normalized_combos: list[dict[str, Any]], tmp_path: Path
) -> None:
    """Test writing combos to Markdown."""
    files = write_markdown_files(normalized_combos, tmp_path, compress=False)

    assert len(files) == 1
    assert files[0] == "combos.md"

    md_file = tmp_path / "combos.md"
    assert md_file.exists()

    content = md_file.read_text()

    # Check that both combos are present
    assert "# combo-1" in content
    assert "# combo-2" in content

    # Check combo 1 details
    assert "Card A" in content
    assert "Card B" in content
    assert "Infinite mana" in content
    assert "Step 1: Do thing A" in content

    # Check combo 2 details
    assert "Card C" in content
    assert "You win the game" in content


def test_parse_spellbook_combos_handles_missing_fields(tmp_path: Path) -> None:
    """Test parsing combos with missing optional fields."""
    # Create a minimal combo with the correct API structure
    minimal_data = {
        "variants": [
            {
                "id": "minimal",
                "uses": [{"card": {"name": "Some Card"}}],
                "produces": [{"feature": {"name": "Some Effect"}}],
            }
        ]
    }

    json_file = tmp_path / "minimal.json"
    with open(json_file, "w") as f:
        json.dump(minimal_data, f)

    combos = list(parse_spellbook_combos(json_file))

    assert len(combos) == 1
    combo = combos[0]
    assert combo["id"] == "minimal"
    assert len(combo["uses"]) == 1
    assert len(combo["produces"]) == 1


def test_parse_spellbook_combos_filters_invalid_cards(tmp_path: Path) -> None:
    """Test that cards without required fields are filtered."""
    combos_data = {
        "variants": [
            {
                "id": "test",
                "uses": [
                    {"card": {"name": "Valid Card", "oracleId": "valid"}},
                    {},  # Invalid - no card field
                    {"card": {}},  # Invalid - empty card
                ],
                "produces": [
                    {"feature": {"name": "Effect"}},
                    {},  # Invalid - no feature field
                    {"feature": {}},  # Invalid - empty feature
                ],
            }
        ]
    }

    json_file = tmp_path / "invalid.json"
    with open(json_file, "w") as f:
        json.dump(combos_data, f)

    combos = list(parse_spellbook_combos(json_file))

    assert len(combos) == 1
    combo = combos[0]

    # Should only have valid cards
    assert len(combo["uses"]) == 1
    assert combo["uses"][0]["name"] == "Valid Card"

    # Should only have valid produces
    assert len(combo["produces"]) == 1
    assert combo["produces"][0]["name"] == "Effect"
