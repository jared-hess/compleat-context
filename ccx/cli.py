"""CLI application for compleat-context."""

import click


@click.group()
def cli() -> None:
    """MTG rules + deckbuilding GPT CLI."""
    pass


@cli.command()
@click.option(
    "--no-compress",
    is_flag=True,
    default=False,
    help="Generate uncompressed output files instead of gzip compressed files.",
)
def build(no_compress: bool) -> None:
    """Download and process Scryfall oracle cards data."""
    from ccx.commands.build import build as run_build

    run_build(compress=not no_compress)


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
