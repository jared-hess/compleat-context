# compleat-context

MTG rules + deckbuilding GPT

A Python 3.12 CLI tool for downloading and processing Magic: The Gathering card data from Scryfall.

## Features

- **Click CLI**: Command-line interface built with [Click](https://click.palletsprojects.com/)
- **Scryfall Integration**: Downloads oracle card data from [Scryfall](https://scryfall.com/)
- **Commander Spellbook Integration**: Downloads and processes combo data from [Commander Spellbook](https://commanderspellbook.com/)
- **Card Filtering**: Automatically filters out non-playable cards (tokens, emblems, art series)
- **DFC Processing**: Merges double-faced card oracle text
- **Data Optimization**: Trims to key fields and deduplicates by oracle_id
- **Multiple Output Formats**: Generates CSV, JSONL, and Markdown files
- **Smart Splitting**: Splits files based on size (CSV: 50MB, JSONL/MD: 2M tokens or 512MB)
- **Streaming Parser**: Uses ijson for memory-efficient processing of large JSON files
- **Token Counting**: Uses tiktoken to ensure files stay within LLM context limits
- **Automated Refresh**: Nightly GitHub Actions workflow to keep data current

## Installation

This project uses [Poetry](https://python-poetry.org/) for dependency management.

```bash
# Install dependencies
poetry install

# Run the CLI
poetry run ccx build
```

## Configuration

All settings have reasonable defaults and can be optionally customized via environment variables or a `.env` file.

### Environment Variables

Create a `.env` file in the project root to customize settings (see `.env.example` for all options):

```bash
# Example .env file
DATA_DIR=/custom/data/path
MAX_FILE_SIZE_MB=100
SCRYFALL_BULK_DATA_URL=https://custom.api.url/bulk-data
```

### Available Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SCRYFALL_BULK_DATA_URL` | `https://api.scryfall.com/bulk-data` | Scryfall bulk data API endpoint |
| `ORACLE_CARDS_TYPE` | `oracle_cards` | Scryfall bulk data type for oracle cards |
| `DEFAULT_CARDS_TYPE` | `default_cards` | Scryfall bulk data type for default cards (pricing) |
| `SPELLBOOK_URL` | `https://json.commanderspellbook.com/variants.json` | Commander Spellbook API endpoint |
| `DATA_DIR` | `data` | Output directory for Scryfall data |
| `SPELLBOOK_DATA_DIR` | `data/spellbook` | Output directory for Spellbook data |
| `MAX_FILE_SIZE_MB` | `50` | Maximum CSV file size in MB before splitting |
| `MAX_FILE_SIZE_BYTES` | `536870912` | Maximum JSONL/MD file size in bytes (512MB) |
| `MAX_TOKENS_PER_FILE` | `2000000` | Maximum tokens per file before splitting |

All settings are optional. If not specified, the defaults will be used.

## Usage

### Build Command

Download and process Scryfall oracle cards data:

```bash
poetry run ccx build
```

This command will:
1. Download the latest oracle cards bulk data from Scryfall
2. **Filter out non-playable cards** (tokens, emblems, art series, memorabilia)
3. Merge oracle text for double-faced cards (DFCs)
4. Download default cards bulk data for pricing information
5. Aggregate prices across all printings and finishes per oracle_id
6. Trim to essential fields (oracle_id, name, mana_cost, type_line, etc.)
7. Deduplicate by oracle_id
8. Convert arrays/objects to valid JSON strings for GPT compatibility
9. Add GPT-friendly flat fields (colors_str, keywords_joined, legal_*, etc.)
10. Write to multiple output formats (CSV, JSONL, Markdown) with intelligent splitting
11. Generate `data/manifest.json` with build metadata

### Commander Spellbook Build Command

Download and process Commander Spellbook combo data:

```bash
poetry run ccx build-spellbook
```

This command will:
1. Download the variants.json file from [Commander Spellbook API](https://json.commanderspellbook.com/variants.json) (~300MB)
2. Stream-parse the JSON using ijson (memory-efficient, never loads full file)
3. Normalize and filter combos to keep only essential fields
4. Generate four output file types in `data/spellbook/`:
   - **jsonl/combos.jsonl** - One JSON object per line with full combo details
   - **csv/combos.csv** - Summary table (id, identity, features, cards, mana costs, popularity)
   - **combo_card_index.jsonl** - Reverse index mapping oracle IDs to combo IDs (at root)
   - **markdown/combos.md** - Human-readable markdown with formatted combo descriptions

#### Uncompressed Output
Use the `--no-compress` flag to generate uncompressed files (`.jsonl`, `.csv`, `.md` instead of `.jsonl.gz`, `.csv.gz`, `.md.gz`):
```bash
poetry run ccx build-spellbook --no-compress
```

**Combo Fields Kept:**
- Top-level: id, status, identity, manaNeeded, manaValueNeeded, description, notes, popularity, bracketTag, legalities, prices, variantCount
- uses[]: card.name, card.oracleId, card.typeLine
- produces[]: feature.name
- Optional: requires, includes

Files are automatically split when they exceed 2M tokens or 512MB, using the same chunking system as Scryfall exports.

### Card Filtering

The build pipeline filters out non-playable cards to ensure only real game cards are included in the dataset. The following card types are excluded:

- **Art Series**: Cards with `layout: "art_series"` or set names containing "Art Series"
- **Tokens**: Cards with `layout: "token"` or `layout: "double_faced_token"`
- **Emblems**: Cards with `layout: "emblem"`
- **Memorabilia**: Cards with `set_type: "memorabilia"`
- **Missing Data**: Cards without both `oracle_text` and `type_line`

This filtering ensures the dataset contains only playable Magic cards suitable for deck building, rules queries, and gameplay analysis.

### Data Pipeline: GPT-Friendly Fields

The build process converts Python-style data to JSON and adds flat fields optimized for LLM/CSV consumption:

**JSON Conversions:**
- `colors`, `color_identity`, `keywords`, `legalities` - Serialized as valid JSON (double-quoted, compact)

**Flat String Fields:**
- `colors_str` - WUBRG-ordered color string (e.g., `"GR"` for Green/Red)
- `color_identity_str` - WUBRG-ordered color identity string
- `keywords_joined` - Semicolon-joined keywords (e.g., `"Haste; Partner"`)

**Legality Fields:**
- `legal_standard`, `legal_pioneer`, `legal_modern`, `legal_legacy`, `legal_vintage`, `legal_pauper`, `legal_commander` - Individual format legality
- `legal_summary` - Human-readable summary (e.g., `"Legal: Modern, Commander • Not legal: Pauper"`)

**Price Aggregation:**
The build process downloads all card printings to compute cheapest, median, and highest USD prices across all finishes (nonfoil, foil, etched). Each oracle row includes seven price fields as flat strings:
- `lowest_price_usd`, `lowest_price_finish`, `lowest_price_set`, `lowest_price_collector`
- `median_price_usd`, `highest_price_usd`
- `price_summary` (human-readable summary, recommended for GPT answers)

**Note:** When using these CSVs with GPT or other tools, prefer the flat fields (`*_str`, `keywords_joined`, `legal_*`, `price_summary`) over parsing JSON for simplicity.

### Output Files

The build process generates three output formats with intelligent splitting based on file size and token count:

#### CSV Files (gzip compressed)
CSV files are written to the `data/` directory:
- **Small datasets (<50MB)**: `data/scryfall_oracle_trimmed.csv.gz`
- **Large datasets (>50MB)**: 
  - `data/scryfall_oracle_trimmed_a-f.csv.gz`
  - `data/scryfall_oracle_trimmed_g-n.csv.gz`
  - `data/scryfall_oracle_trimmed_o-z.csv.gz`

#### JSONL Files (gzip compressed)
JSONL files are written to the `data/jsonl/` directory. Files are split when they exceed 2,000,000 tokens or 512MB:
- `data/jsonl/scryfall_oracle_trimmed.jsonl.gz` (or `scryfall_oracle_trimmed_1.jsonl.gz`, `scryfall_oracle_trimmed_2.jsonl.gz`, etc. if split)

Each line contains a complete card object as valid JSON.

#### Markdown Files (gzip compressed)
Markdown files are written to the `data/markdown/` directory. Files are split when they exceed 2,000,000 tokens or 512MB:
- `data/markdown/scryfall_oracle_trimmed.md.gz` (or `scryfall_oracle_trimmed_1.md.gz`, `scryfall_oracle_trimmed_2.md.gz`, etc. if split)

Cards are formatted with headers and field labels for easy reading.

#### Uncompressed Output
Use the `--no-compress` flag to generate uncompressed files (`.csv`, `.jsonl`, `.md` instead of `.csv.gz`, `.jsonl.gz`, `.md.gz`):
```bash
poetry run ccx build --no-compress
```

#### Metadata
- `data/manifest.json` - Lists all generated files with build timestamp
- `data/spellbook/` - Commander Spellbook combo artifacts
  - `jsonl/combos.jsonl` - JSONL format combos
  - `csv/combos.csv` - CSV summary table
  - `combo_card_index.jsonl` - Oracle ID to combo ID index
  - `markdown/combos.md` - Human-readable markdown

**Note:** Token counting uses tiktoken (cl100k_base encoding, same as GPT-4) to ensure files stay within LLM context limits.

## Development

### Pre-commit Hooks

This project uses pre-commit hooks for code quality:

```bash
# Install pre-commit hooks
poetry run pre-commit install

# Run manually
poetry run pre-commit run --all-files
```

Configured tools:
- **black**: Code formatting
- **ruff**: Linting with auto-fix
- **mypy**: Type checking

### Testing

Run tests with pytest:

```bash
poetry run pytest -v
```

### CI/CD

GitHub Actions workflows:
- **CI** (`ci.yml`): Runs on push/PR - lint, format check, type check, and tests
- **Nightly Refresh** (`nightly.yml`): Runs daily at 2 AM UTC - updates Scryfall and Commander Spellbook data, commits changes

The nightly workflow can be controlled with the `SPELLBOOK_ENABLED` repository variable (set to `"true"` or `"false"`).

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Credits

- **Scryfall**: Card data provided by [Scryfall](https://scryfall.com/), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- **Commander Spellbook**: Combo data provided by [Commander Spellbook](https://commanderspellbook.com/)
- **Magic: The Gathering**: Card names, text, and artwork are property of Wizards of the Coast
- Built with [Click](https://click.palletsprojects.com/), [Pandas](https://pandas.pydata.org/), [Requests](https://requests.readthedocs.io/), [ijson](https://github.com/ICRAR/ijson), and [tiktoken](https://github.com/openai/tiktoken)

## Disclaimer

This project is not affiliated with or endorsed by Wizards of the Coast, Scryfall, or Commander Spellbook.
