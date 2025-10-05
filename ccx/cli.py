"""CLI application for compleat-context."""

import click


@click.group()
def cli() -> None:
    """MTG rules + deckbuilding GPT CLI."""
    pass


@cli.command()
def build() -> None:
    """Download and process Scryfall oracle cards data."""
    from ccx.commands.build import build as run_build

    run_build()


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
