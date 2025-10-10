"""Build command for Commander Spellbook combo data."""

import gzip
import json
import os
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import click
import ijson  # type: ignore[import-untyped]
import pandas as pd
import requests

from ccx.commands.build import MAX_FILE_SIZE_BYTES, MAX_TOKENS_PER_FILE, count_tokens

SPELLBOOK_URL = "https://json.commanderspellbook.com/variants.json"
DATA_DIR = Path("data/spellbook")


def download_spellbook_data(src: str, cache_path: Path, force: bool = False) -> Path:
    """Download Commander Spellbook data with conditional download support.

    Args:
        src: URL or local path to the source file
        cache_path: Path to cache the downloaded file
        force: Force download even if cached file exists

    Returns:
        Path to the downloaded/cached file
    """
    # If src is a local file, just return it
    if os.path.exists(src):
        click.echo(f"Using local file: {src}")
        return Path(src)

    # Check if we have a cached version
    if cache_path.exists() and not force:
        click.echo(f"Using cached file: {cache_path}")
        # Try conditional download
        headers = {}
        if cache_path.exists():
            mtime = cache_path.stat().st_mtime
            headers["If-Modified-Since"] = datetime.utcfromtimestamp(mtime).strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            )

        click.echo(f"Checking for updates from {src}...")
        response = requests.head(src, headers=headers, timeout=30)

        if response.status_code == 304:
            click.echo("Cached file is up to date")
            return cache_path
        elif response.status_code != 200:
            click.echo(
                f"Warning: HEAD request returned {response.status_code}, "
                "using cached file"
            )
            return cache_path

    # Download the file
    click.echo(f"Downloading from {src}...")
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    response = requests.get(src, stream=True, timeout=60)
    response.raise_for_status()

    # Get total file size for progress bar
    total_size = int(response.headers.get("content-length", 0))

    # Write to cache with streaming and progress bar
    with open(cache_path, "wb") as f:
        if total_size > 0:
            with click.progressbar(
                length=total_size,
                label="Downloading",
                show_eta=True,
                show_percent=True,
            ) as bar:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    bar.update(len(chunk))
        else:
            # Fallback if content-length is not available
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

    file_size_mb = cache_path.stat().st_size / (1024 * 1024)
    click.echo(f"Downloaded {file_size_mb:.2f} MB to {cache_path}")

    return cache_path


def open_json_file(path: Path) -> Any:
    """Open JSON file, handling both .json and .json.gz formats."""
    if path.suffix == ".gz":
        return gzip.open(path, "rb")
    else:
        return open(path, "rb")


def parse_spellbook_combos(file_path: Path) -> Iterator[dict[str, Any]]:
    """Stream-parse Commander Spellbook variants.json using ijson.

    Yields normalized combo dictionaries with only the fields we want to keep.
    """
    with open_json_file(file_path) as f:
        # Parse the variants array items from the top-level object
        combos = ijson.items(f, "variants.item")

        for combo in combos:
            # Normalize the combo, keeping only specified fields
            normalized = {}

            # Top-level fields
            for field in [
                "id",
                "status",
                "identity",
                "manaNeeded",
                "manaValueNeeded",
                "description",
                "notes",
                "popularity",
                "bracketTag",
                "legalities",
                "prices",
                "variantCount",
            ]:
                if field in combo:
                    normalized[field] = combo[field]

            # Parse uses[] - keep card.name, card.oracleId, card.typeLine
            if "uses" in combo and isinstance(combo["uses"], list):
                normalized["uses"] = []
                for item in combo["uses"]:
                    if "card" in item and isinstance(item["card"], dict):
                        card = item["card"]
                        card_info = {}
                        if "name" in card:
                            card_info["name"] = card["name"]
                        if "oracleId" in card:
                            card_info["oracleId"] = card["oracleId"]
                        if "typeLine" in card:
                            card_info["typeLine"] = card["typeLine"]
                        if card_info:  # Only add if we got at least one field
                            normalized["uses"].append(card_info)

            # Parse produces[] - keep feature.name
            if "produces" in combo and isinstance(combo["produces"], list):
                normalized["produces"] = []
                for item in combo["produces"]:
                    if "feature" in item and isinstance(item["feature"], dict):
                        feature = item["feature"]
                        if "name" in feature:
                            normalized["produces"].append({"name": feature["name"]})

            # Optional passthrough fields
            for field in ["requires", "includes"]:
                if field in combo:
                    normalized[field] = combo[field]

            yield normalized


def write_jsonl_files(
    combos: list[dict[str, Any]], output_dir: Path, compress: bool = True
) -> list[str]:
    """Write combos to JSONL file(s), splitting if > 2M tokens or 512MB."""
    output_dir.mkdir(parents=True, exist_ok=True)

    written_files = []
    current_file_index = 1
    current_lines: list[str] = []
    current_tokens = 0
    current_size_bytes = 0

    file_ext = ".jsonl.gz" if compress else ".jsonl"

    for combo in combos:
        json_line = json.dumps(combo, ensure_ascii=False) + "\n"

        # Count tokens and size
        line_tokens = count_tokens(json_line)
        line_bytes = len(json_line.encode("utf-8"))

        # Check if we need to split
        if current_lines and (
            current_tokens + line_tokens > MAX_TOKENS_PER_FILE
            or current_size_bytes + line_bytes > MAX_FILE_SIZE_BYTES
        ):
            # Write current batch
            filename = (
                f"combos_{current_file_index}{file_ext}"
                if current_file_index > 1
                else f"combos{file_ext}"
            )
            output_path = output_dir / filename

            if compress:
                with gzip.open(output_path, "wt", encoding="utf-8") as f:
                    f.writelines(current_lines)
            else:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.writelines(current_lines)

            click.echo(
                f"Wrote {len(current_lines)} combos to {filename} "
                f"({current_tokens:,} tokens, "
                f"{current_size_bytes / (1024 * 1024):.2f} MB)"
            )
            written_files.append(filename)

            # Reset for next batch
            current_file_index += 1
            current_lines = []
            current_tokens = 0
            current_size_bytes = 0

        current_lines.append(json_line)
        current_tokens += line_tokens
        current_size_bytes += line_bytes

    # Write remaining combos
    if current_lines:
        filename = (
            f"combos_{current_file_index}{file_ext}"
            if current_file_index > 1
            else f"combos{file_ext}"
        )
        output_path = output_dir / filename

        if compress:
            with gzip.open(output_path, "wt", encoding="utf-8") as f:
                f.writelines(current_lines)
        else:
            with open(output_path, "w", encoding="utf-8") as f:
                f.writelines(current_lines)

        click.echo(
            f"Wrote {len(current_lines)} combos to {filename} "
            f"({current_tokens:,} tokens, "
            f"{current_size_bytes / (1024 * 1024):.2f} MB)"
        )
        written_files.append(filename)

    return written_files


def _write_csv_files(
    combos: list[dict[str, Any]], output_dir: Path, compress: bool = True
) -> list[str]:
    """Write combos to CSV with summary columns."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build summary rows
    rows = []
    for combo in combos:
        row: dict[str, Any] = {
            "id": combo.get("id", ""),
            "identity": combo.get("identity", ""),
            "manaNeeded": combo.get("manaNeeded", ""),
            "manaValueNeeded": combo.get("manaValueNeeded", ""),
            "popularity": combo.get("popularity", ""),
        }

        # Extract features
        features = []
        if "produces" in combo and isinstance(combo["produces"], list):
            for item in combo["produces"]:
                if "name" in item:
                    features.append(item["name"])
        row["features"] = "; ".join(features)

        # Extract cards
        cards = []
        if "uses" in combo and isinstance(combo["uses"], list):
            for item in combo["uses"]:
                if "name" in item:
                    cards.append(item["name"])

        # Add individual card columns
        row["card1"] = cards[0] if len(cards) > 0 else ""
        row["card2"] = cards[1] if len(cards) > 1 else ""
        row["card3"] = cards[2] if len(cards) > 2 else ""
        row["card_count"] = len(cards)

        rows.append(row)

    # Create DataFrame
    df = pd.DataFrame(rows)

    # Write CSV
    file_ext = ".csv.gz" if compress else ".csv"
    filename = f"combos{file_ext}"
    output_path = output_dir / filename

    if compress:
        with gzip.open(output_path, "wt", encoding="utf-8") as f:
            df.to_csv(f, index=False)
    else:
        df.to_csv(output_path, index=False)

    click.echo(
        f"Wrote {len(df)} combos to {filename} "
        f"({output_path.stat().st_size / (1024 * 1024):.2f} MB)"
    )

    return [filename]


def _write_card_index(
    combos: list[dict[str, Any]], output_dir: Path, compress: bool = True
) -> list[str]:
    """Write combo_card_index.jsonl mapping oracleId to combo_ids."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build index: oracleId -> {name, combo_ids[]}
    index: dict[str, dict[str, Any]] = {}

    for combo in combos:
        combo_id = combo.get("id")
        if not combo_id:
            continue

        if "uses" in combo and isinstance(combo["uses"], list):
            for card in combo["uses"]:
                oracle_id = card.get("oracleId")
                name = card.get("name", "")

                if not oracle_id:
                    continue

                if oracle_id not in index:
                    index[oracle_id] = {
                        "oracleId": oracle_id,
                        "name": name,
                        "combo_ids": [],
                    }

                if combo_id not in index[oracle_id]["combo_ids"]:
                    index[oracle_id]["combo_ids"].append(combo_id)

    # Write JSONL
    file_ext = ".jsonl.gz" if compress else ".jsonl"
    filename = f"combo_card_index{file_ext}"
    output_path = output_dir / filename

    lines = []
    for entry in sorted(index.values(), key=lambda x: x["name"]):
        lines.append(json.dumps(entry, ensure_ascii=False) + "\n")

    if compress:
        with gzip.open(output_path, "wt", encoding="utf-8") as f:
            f.writelines(lines)
    else:
        with open(output_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    click.echo(
        f"Wrote {len(index)} oracle IDs to {filename} "
        f"({output_path.stat().st_size / (1024 * 1024):.2f} MB)"
    )

    return [filename]


def write_markdown_files(
    combos: list[dict[str, Any]], output_dir: Path, compress: bool = True
) -> list[str]:
    """Write combos to Markdown file(s), splitting if > 2M tokens or 512MB."""
    output_dir.mkdir(parents=True, exist_ok=True)

    written_files = []
    current_file_index = 1
    current_lines: list[str] = []
    current_tokens = 0
    current_size_bytes = 0

    file_ext = ".md.gz" if compress else ".md"

    for combo in combos:
        # Build markdown for this combo
        md_lines = []

        # Heading
        combo_id = combo.get("id", "unknown")
        md_lines.append(f"# {combo_id}\n\n")

        # Cards
        if "uses" in combo and isinstance(combo["uses"], list):
            md_lines.append("**Cards:**\n\n")
            for card in combo["uses"]:
                card_name = card.get("name", "Unknown")
                md_lines.append(f"- {card_name}\n")
            md_lines.append("\n")

        # Produces
        if "produces" in combo and isinstance(combo["produces"], list):
            features = [p.get("name", "") for p in combo["produces"] if "name" in p]
            if features:
                md_lines.append(f"**Produces:** {', '.join(features)}\n\n")

        # Metadata
        metadata = []
        if "manaNeeded" in combo:
            metadata.append(f"Mana: {combo['manaNeeded']}")
        if "manaValueNeeded" in combo:
            metadata.append(f"MV: {combo['manaValueNeeded']}")
        if "identity" in combo:
            metadata.append(f"Colors: {combo['identity']}")
        if "popularity" in combo:
            metadata.append(f"Popularity: {combo['popularity']}")

        if metadata:
            md_lines.append(f"**{', '.join(metadata)}**\n\n")

        # Steps (description)
        if "description" in combo:
            md_lines.append("**Steps:**\n\n")
            md_lines.append(f"{combo['description']}\n\n")

        md_lines.append("---\n\n")

        combo_md = "".join(md_lines)

        # Count tokens and size
        combo_tokens = count_tokens(combo_md)
        combo_bytes = len(combo_md.encode("utf-8"))

        # Check if we need to split
        if current_lines and (
            current_tokens + combo_tokens > MAX_TOKENS_PER_FILE
            or current_size_bytes + combo_bytes > MAX_FILE_SIZE_BYTES
        ):
            # Write current batch
            filename = (
                f"combos_{current_file_index}{file_ext}"
                if current_file_index > 1
                else f"combos{file_ext}"
            )
            output_path = output_dir / filename

            content = "".join(current_lines)
            if compress:
                with gzip.open(output_path, "wt", encoding="utf-8") as f:
                    f.write(content)
            else:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(content)

            click.echo(
                f"Wrote {len(current_lines)} combos to {filename} "
                f"({current_tokens:,} tokens, "
                f"{current_size_bytes / (1024 * 1024):.2f} MB)"
            )
            written_files.append(filename)

            # Reset for next batch
            current_file_index += 1
            current_lines = []
            current_tokens = 0
            current_size_bytes = 0

        current_lines.append(combo_md)
        current_tokens += combo_tokens
        current_size_bytes += combo_bytes

    # Write remaining combos
    if current_lines:
        filename = (
            f"combos_{current_file_index}{file_ext}"
            if current_file_index > 1
            else f"combos{file_ext}"
        )
        output_path = output_dir / filename

        content = "".join(current_lines)
        if compress:
            with gzip.open(output_path, "wt", encoding="utf-8") as f:
                f.write(content)
        else:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)

        click.echo(
            f"Wrote {len(current_lines)} combos to {filename} "
            f"({current_tokens:,} tokens, "
            f"{current_size_bytes / (1024 * 1024):.2f} MB)"
        )
        written_files.append(filename)

    return written_files


def write_output_files(
    combos: list[dict[str, Any]], output_dir: Path, compress: bool = True
) -> list[str]:
    """Write combos to CSV/GZ, JSONL/GZ, and MD/GZ files with appropriate splitting."""
    output_dir.mkdir(parents=True, exist_ok=True)

    all_written_files = []

    # Write JSONL files to jsonl subdirectory
    click.echo("Writing JSONL files...")
    jsonl_dir = output_dir / "jsonl"
    jsonl_files = write_jsonl_files(combos, jsonl_dir, compress=compress)
    # Prepend directory to filenames
    all_written_files.extend([f"jsonl/{f}" for f in jsonl_files])

    # Write CSV files to csv subdirectory
    click.echo("Writing CSV files...")
    csv_dir = output_dir / "csv"
    csv_files = _write_csv_files(combos, csv_dir, compress=compress)
    # Prepend directory to filenames
    all_written_files.extend([f"csv/{f}" for f in csv_files])

    # Write card index to root of spellbook directory
    click.echo("Writing card index...")
    index_files = _write_card_index(combos, output_dir, compress=compress)
    all_written_files.extend(index_files)

    # Write Markdown files to markdown subdirectory
    click.echo("Writing Markdown files...")
    md_dir = output_dir / "markdown"
    md_files = write_markdown_files(combos, md_dir, compress=compress)
    # Prepend directory to filenames
    all_written_files.extend([f"markdown/{f}" for f in md_files])

    return all_written_files


def build_spellbook(compress: bool = True) -> None:
    """Download and process Commander Spellbook combo data."""
    click.echo("Starting Commander Spellbook build...")

    # Download/cache the source file
    cache_dir = Path("/tmp/spellbook_cache")
    cache_path = cache_dir / "variants.json"

    try:
        source_file = download_spellbook_data(SPELLBOOK_URL, cache_path)
    except Exception as e:
        click.echo(f"Error downloading spellbook data: {e}", err=True)
        raise SystemExit(1)

    # Parse combos with streaming
    click.echo("Parsing combos with streaming parser...")
    try:
        combos = list(parse_spellbook_combos(source_file))
        click.echo(f"Parsed {len(combos)} combos")
    except Exception as e:
        click.echo(f"Error parsing spellbook data: {e}", err=True)
        raise SystemExit(1)

    if not combos:
        click.echo("Warning: No combos found in source file", err=True)
        raise SystemExit(1)

    # Write output files
    click.echo("Writing output files...")
    try:
        written_files = write_output_files(combos, DATA_DIR, compress=compress)
    except Exception as e:
        click.echo(f"Error writing output files: {e}", err=True)
        raise SystemExit(1)

    click.echo(f"\nSpellbook build complete! Generated {len(written_files)} files:")
    for filename in written_files:
        click.echo(f"  - {filename}")
