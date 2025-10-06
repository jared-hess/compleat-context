"""Build command - downloads and processes Scryfall data."""

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click
import pandas as pd
import requests

SCRYFALL_BULK_DATA_URL = "https://api.scryfall.com/bulk-data"
ORACLE_CARDS_TYPE = "oracle_cards"
DEFAULT_CARDS_TYPE = "default_cards"
DATA_DIR = Path("data")
MAX_FILE_SIZE_MB = 50
WUBRG = ["W", "U", "B", "R", "G"]


def to_json(v: Any) -> str:
    """Convert value to valid JSON string with compact separators."""
    # Convert None to empty list/dict for consistency with existing data
    if v is None:
        v = []
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def colors_str(lst: list[str] | None) -> str:
    """Convert color list to WUBRG-ordered string (e.g., ['G','R'] -> 'GR')."""
    s = set(lst or [])
    return "".join(c for c in WUBRG if c in s)


def build_legal_summary(leg: dict[str, str]) -> str:
    """Build human-readable legal summary from legalities dict."""
    legal = [k for k, v in leg.items() if v == "legal"]
    not_legal = [k for k, v in leg.items() if v == "not_legal"]
    banned = [k for k, v in leg.items() if v == "banned"]
    parts = []
    if legal:
        parts.append("Legal: " + ", ".join(sorted(legal)))
    if not_legal:
        parts.append("Not legal: " + ", ".join(sorted(not_legal)))
    if banned:
        parts.append("Banned: " + ", ".join(sorted(banned)))
    return " • ".join(parts)


def download_scryfall_data(bulk_type: str = ORACLE_CARDS_TYPE) -> list[dict[str, Any]]:
    """Download Scryfall bulk data."""
    click.echo(f"Fetching bulk data info from {SCRYFALL_BULK_DATA_URL}...")
    response = requests.get(SCRYFALL_BULK_DATA_URL, timeout=30)
    response.raise_for_status()
    bulk_data_list = response.json()["data"]

    # Find the oracle_cards bulk data
    oracle_data_info = next(
        (item for item in bulk_data_list if item["type"] == bulk_type), None
    )
    if not oracle_data_info:
        raise ValueError(f"Could not find bulk data type: {bulk_type}")

    download_url = oracle_data_info["download_uri"]
    click.echo(f"Downloading from {download_url}...")

    response = requests.get(download_url, timeout=300)
    response.raise_for_status()

    cards: list[dict[str, Any]] = response.json()
    click.echo(f"Downloaded {len(cards)} cards")
    return cards


def _best_price_from_printing(prices: dict[str, Any]) -> list[tuple[str, float]]:
    """Extract numeric USD prices from a printing's prices dict.

    Returns list of (finish, price) tuples for usd, usd_foil, usd_etched.
    """
    result = []

    # Map price keys to finish types
    price_map = [
        ("usd", "nonfoil"),
        ("usd_foil", "foil"),
        ("usd_etched", "etched"),
    ]

    for price_key, finish in price_map:
        price_str = prices.get(price_key)
        if price_str:
            try:
                price_val = float(price_str)
                result.append((finish, price_val))
            except (ValueError, TypeError):
                # Skip invalid price strings
                pass

    return result


def build_oracle_price_index(
    default_cards: list[dict[str, Any]]
) -> dict[str, dict[str, str]]:
    """Build price index from default_cards, aggregating by oracle_id.

    For each oracle_id, computes:
    - lowest_price_usd, lowest_price_finish, lowest_price_set, lowest_price_collector
    - median_price_usd, highest_price_usd
    - price_summary string

    Returns dict mapping oracle_id -> dict of price fields (all strings).
    """
    from statistics import median

    # Collect all prices per oracle_id
    oracle_prices: dict[str, list[tuple[float, str, str, str]]] = {}

    for card in default_cards:
        oracle_id = card.get("oracle_id")
        if not oracle_id:
            continue

        prices = card.get("prices")
        if not prices:
            continue

        set_code = card.get("set", "")
        collector_number = card.get("collector_number", "")

        # Extract all USD prices for this printing
        for finish, price_val in _best_price_from_printing(prices):
            if oracle_id not in oracle_prices:
                oracle_prices[oracle_id] = []
            oracle_prices[oracle_id].append(
                (price_val, finish, set_code, collector_number)
            )

    # Build the index
    price_index: dict[str, dict[str, str]] = {}

    for oracle_id, price_list in oracle_prices.items():
        if not price_list:
            continue

        # Sort by price to find min/max
        price_list.sort(key=lambda x: x[0])

        # Extract just the price values for median/highest
        price_values = [p[0] for p in price_list]

        # Cheapest
        lowest_price, lowest_finish, lowest_set, lowest_collector = price_list[0]

        # Median and highest
        median_price = median(price_values)
        highest_price = price_values[-1]

        # Build price_summary
        summary_parts = [f"${lowest_price:.2f}"]
        summary_parts.append(
            f"(cheapest: {lowest_set.upper()} #{lowest_collector}, {lowest_finish})"
        )

        # Add range/median if there are multiple prices
        if len(price_values) > 1:
            summary_parts.append(f"Range ${lowest_price:.2f}–${highest_price:.2f}.")
            summary_parts.append(f"median ${median_price:.2f}.")

        price_summary = " ".join(summary_parts)

        price_index[oracle_id] = {
            "lowest_price_usd": f"{lowest_price:.2f}",
            "lowest_price_finish": lowest_finish,
            "lowest_price_set": lowest_set,
            "lowest_price_collector": lowest_collector,
            "median_price_usd": f"{median_price:.2f}",
            "highest_price_usd": f"{highest_price:.2f}",
            "price_summary": price_summary,
        }

    return price_index


def filter_playable_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter out non-playable cards (art cards, tokens, emblems, etc.).

    This function removes:
    - Art series cards (layout: "art_series")
    - Tokens (layout: "token", "double_faced_token")
    - Emblems (layout: "emblem")
    - Memorabilia (set_type: "memorabilia")
    - Art Series cards (set_name contains "Art Series")
    - Cards without oracle_text or type_line
    """
    playable_cards = []

    for card in cards:
        # Filter by layout
        layout = card.get("layout", "")
        if layout in {"art_series", "token", "double_faced_token", "emblem"}:
            continue

        # Filter by set_type
        set_type = card.get("set_type", "")
        if set_type == "memorabilia":
            continue

        # Filter by set_name (Art Series fallback)
        set_name = card.get("set_name", "")
        if "Art Series" in set_name:
            continue

        # Require oracle_text or type_line
        oracle_text = card.get("oracle_text", "")
        type_line = card.get("type_line", "")
        if not oracle_text and not type_line:
            continue

        playable_cards.append(card)

    return playable_cards


def merge_dfc_oracle_text(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge double-faced card oracle text."""
    processed_cards = []

    for card in cards:
        card_copy = card.copy()

        # Check if this is a double-faced card with card_faces
        if "card_faces" in card and len(card["card_faces"]) > 0:
            # Merge oracle text from all faces
            oracle_texts = [
                face.get("oracle_text", "")
                for face in card["card_faces"]
                if face.get("oracle_text")
            ]
            if oracle_texts:
                card_copy["oracle_text"] = " // ".join(oracle_texts)

        processed_cards.append(card_copy)

    return processed_cards


def trim_and_dedupe_cards(
    cards: list[dict[str, Any]],
    price_index: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Trim to key fields and deduplicate by oracle_id."""
    # Key fields to keep from original data
    fields_to_keep = [
        "oracle_id",
        "name",
        "mana_cost",
        "cmc",
        "type_line",
        "oracle_text",
        "reserved",
        "set",
        "set_name",
        "rarity",
        "lowest_price_usd",
        "lowest_price_finish",
        "lowest_price_set",
        "lowest_price_collector",
        "median_price_usd",
        "highest_price_usd",
        "price_summary",
    ]

    trimmed_cards = []
    for card in cards:
        # Start with basic fields
        trimmed_card = {
            field: card.get(field, None) for field in fields_to_keep if field in card
        }

        # Convert colors to JSON and add flat string
        colors = card.get("colors", [])
        trimmed_card["colors"] = to_json(colors)
        trimmed_card["colors_str"] = colors_str(colors)

        # Convert color_identity to JSON and add flat string
        color_identity = card.get("color_identity", [])
        trimmed_card["color_identity"] = to_json(color_identity)
        trimmed_card["color_identity_str"] = colors_str(color_identity)

        # Convert keywords to JSON and add joined string
        keywords = card.get("keywords", [])
        trimmed_card["keywords"] = to_json(keywords)
        trimmed_card["keywords_joined"] = "; ".join(keywords)

        # Convert legalities to JSON and add individual format fields
        legalities = card.get("legalities", {})
        trimmed_card["legalities"] = to_json(legalities)
        for fmt in [
            "standard",
            "pioneer",
            "modern",
            "legacy",
            "vintage",
            "pauper",
            "commander",
        ]:
            trimmed_card[f"legal_{fmt}"] = legalities.get(fmt, "")
        trimmed_card["legal_summary"] = build_legal_summary(legalities)

        trimmed_cards.append(trimmed_card)

    # Convert to DataFrame for deduplication
    df = pd.DataFrame(trimmed_cards)

    # Deduplicate by oracle_id, keeping first occurrence
    if "oracle_id" in df.columns:
        df = df.drop_duplicates(subset=["oracle_id"], keep="first")

    # Merge price data if provided
    if price_index and "oracle_id" in df.columns:
        # Add price columns with empty strings as default
        for field in [
            "lowest_price_usd",
            "lowest_price_finish",
            "lowest_price_set",
            "lowest_price_collector",
            "median_price_usd",
            "highest_price_usd",
            "price_summary",
        ]:
            if field not in df.columns:
                df[field] = ""

        # Update with price data
        for idx in df.index:
            oracle_id = df.loc[idx, "oracle_id"]
            if oracle_id and oracle_id in price_index:
                for field, value in price_index[oracle_id].items():
                    df.loc[idx, field] = value

    result: list[dict[str, Any]] = df.to_dict("records")  # type: ignore[assignment]
    return result


def write_output_files(cards: list[dict[str, Any]], output_dir: Path) -> list[str]:
    """Write cards to CSV/GZ files, splitting alphabetically if > 50MB."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Convert to DataFrame
    df = pd.DataFrame(cards)

    # Sort by name for consistent alphabetical splitting
    if "name" in df.columns:
        df = df.sort_values("name")

    # Write to a temporary file to check size
    temp_file = output_dir / "scryfall_oracle_trimmed.csv"
    df.to_csv(temp_file, index=False)

    file_size_mb = temp_file.stat().st_size / (1024 * 1024)
    click.echo(f"Total file size: {file_size_mb:.2f} MB")

    written_files = []

    if file_size_mb > MAX_FILE_SIZE_MB:
        # Split into a-f, g-n, o-z
        click.echo(f"File size exceeds {MAX_FILE_SIZE_MB} MB, splitting...")

        # Define alphabetical ranges
        ranges = [
            ("a", "f", "scryfall_oracle_trimmed_a-f.csv.gz"),
            ("g", "n", "scryfall_oracle_trimmed_g-n.csv.gz"),
            ("o", "z", "scryfall_oracle_trimmed_o-z.csv.gz"),
        ]

        for start, end, filename in ranges:
            # Filter cards by first letter of name
            mask = df["name"].str.lower().str[0].between(start, end)
            subset_df = df[mask]

            if len(subset_df) > 0:
                output_path = output_dir / filename
                with gzip.open(output_path, "wt", encoding="utf-8") as f:
                    subset_df.to_csv(f, index=False)
                click.echo(
                    f"Wrote {len(subset_df)} cards to {filename} "
                    f"({output_path.stat().st_size / (1024 * 1024):.2f} MB)"
                )
                written_files.append(filename)

        # Remove the temporary uncompressed file
        temp_file.unlink()
    else:
        # Write as a single compressed file
        output_file = output_dir / "scryfall_oracle_trimmed.csv.gz"
        with gzip.open(output_file, "wt", encoding="utf-8") as f:
            df.to_csv(f, index=False)

        click.echo(
            f"Wrote {len(df)} cards to scryfall_oracle_trimmed.csv.gz "
            f"({output_file.stat().st_size / (1024 * 1024):.2f} MB)"
        )
        written_files.append("scryfall_oracle_trimmed.csv.gz")

        # Remove the temporary uncompressed file if it exists
        if temp_file.exists():
            temp_file.unlink()

    return written_files


def write_manifest(files: list[str], output_dir: Path) -> None:
    """Write manifest.json with metadata about the build."""

    manifest = {
        "build_date": datetime.now(UTC).isoformat(),
        "files": files,
        "total_files": len(files),
    }

    manifest_path = output_dir / "manifest.json"
    with manifest_path.open("w") as f:
        json.dump(manifest, f, indent=2)

    click.echo(f"Wrote manifest to {manifest_path}")


def build() -> None:
    """Download and process Scryfall oracle cards data."""
    click.echo("Starting build process...")

    # Download oracle cards data
    cards = download_scryfall_data(ORACLE_CARDS_TYPE)

    # Filter out non-playable cards
    click.echo("Filtering out non-playable cards...")
    original_count = len(cards)
    cards = filter_playable_cards(cards)
    filtered_count = len(cards)
    click.echo(f"Filtered {original_count - filtered_count} non-playable cards "
               f"({filtered_count} remaining)")

    # Merge DFC oracle text
    click.echo("Merging DFC oracle text...")
    cards = merge_dfc_oracle_text(cards)

    # Download default_cards for price data
    click.echo("Downloading default_cards for price data...")
    default_cards = download_scryfall_data(DEFAULT_CARDS_TYPE)

    # Build price index
    click.echo("Building price index...")
    price_index = build_oracle_price_index(default_cards)
    click.echo(f"Indexed prices for {len(price_index)} cards")

    # Trim and deduplicate, merging price data
    click.echo("Trimming fields and deduplicating...")
    cards = trim_and_dedupe_cards(cards, price_index)

    # Write output files
    click.echo("Writing output files...")
    written_files = write_output_files(cards, DATA_DIR)

    # Write manifest
    write_manifest(written_files, DATA_DIR)

    click.echo("Build complete!")
