# compleat-context

MTG rules + deckbuilding GPT

A Python 3.12 CLI tool for downloading and processing Magic: The Gathering card data from Scryfall.

## Features

- **Click CLI**: Command-line interface built with [Click](https://click.palletsprojects.com/)
- **Scryfall Integration**: Downloads oracle card data from [Scryfall](https://scryfall.com/)
- **DFC Processing**: Merges double-faced card oracle text
- **Data Optimization**: Trims to key fields and deduplicates by oracle_id
- **Smart Splitting**: Automatically splits large files (>50MB) alphabetically (a-f, g-n, o-z)
- **Automated Refresh**: Nightly GitHub Actions workflow to keep data current

## Installation

This project uses [Poetry](https://python-poetry.org/) for dependency management.

```bash
# Install dependencies
poetry install

# Run the CLI
poetry run ccx build
```

## Usage

### Build Command

Download and process Scryfall oracle cards data:

```bash
poetry run ccx build
```

This command will:
1. Download the latest oracle cards bulk data from Scryfall
2. Merge oracle text for double-faced cards (DFCs)
3. Download default cards bulk data for pricing information
4. Aggregate prices across all printings and finishes per oracle_id
5. Trim to essential fields (oracle_id, name, mana_cost, type_line, etc.)
6. Deduplicate by oracle_id
7. Write to `data/scryfall_oracle_trimmed.csv.gz` (or split files if >50MB)
8. Generate `data/manifest.json` with build metadata

**Price Aggregation**: The build process downloads all card printings to compute cheapest, median, and highest USD prices across all finishes (nonfoil, foil, etched). Each oracle row includes seven price fields as flat strings:
- `lowest_price_usd`, `lowest_price_finish`, `lowest_price_set`, `lowest_price_collector`
- `median_price_usd`, `highest_price_usd`
- `price_summary` (human-readable summary, recommended for GPT answers)

### Output Files

- **Small datasets (<50MB)**: `data/scryfall_oracle_trimmed.csv.gz`
- **Large datasets (>50MB)**: 
  - `data/scryfall_oracle_trimmed_a-f.csv.gz`
  - `data/scryfall_oracle_trimmed_g-n.csv.gz`
  - `data/scryfall_oracle_trimmed_o-z.csv.gz`
- **Metadata**: `data/manifest.json`

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
- **Nightly Refresh** (`nightly.yml`): Runs daily at 2 AM UTC - updates data files and commits changes

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Credits

- **Scryfall**: Card data provided by [Scryfall](https://scryfall.com/), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- **Magic: The Gathering**: Card names, text, and artwork are property of Wizards of the Coast
- Built with [Click](https://click.palletsprojects.com/), [Pandas](https://pandas.pydata.org/), and [Requests](https://requests.readthedocs.io/)

## Disclaimer

This project is not affiliated with or endorsed by Wizards of the Coast or Scryfall.
