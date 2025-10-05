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
DATA_DIR = Path("data")
MAX_FILE_SIZE_MB = 50


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
) -> list[dict[str, Any]]:
    """Trim to key fields and deduplicate by oracle_id."""
    # Key fields to keep
    fields_to_keep = [
        "oracle_id",
        "name",
        "mana_cost",
        "cmc",
        "type_line",
        "oracle_text",
        "colors",
        "color_identity",
        "keywords",
        "legalities",
        "reserved",
        "set",
        "set_name",
        "rarity",
    ]

    trimmed_cards = []
    for card in cards:
        trimmed_card = {
            field: card.get(field, None) for field in fields_to_keep if field in card
        }
        trimmed_cards.append(trimmed_card)

    # Convert to DataFrame for deduplication
    df = pd.DataFrame(trimmed_cards)

    # Deduplicate by oracle_id, keeping first occurrence
    if "oracle_id" in df.columns:
        df = df.drop_duplicates(subset=["oracle_id"], keep="first")

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

    # Download data
    cards = download_scryfall_data()

    # Merge DFC oracle text
    click.echo("Merging DFC oracle text...")
    cards = merge_dfc_oracle_text(cards)

    # Trim and deduplicate
    click.echo("Trimming fields and deduplicating...")
    cards = trim_and_dedupe_cards(cards)

    # Write output files
    click.echo("Writing output files...")
    written_files = write_output_files(cards, DATA_DIR)

    # Write manifest
    write_manifest(written_files, DATA_DIR)

    click.echo("Build complete!")
