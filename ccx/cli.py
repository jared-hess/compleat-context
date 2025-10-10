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


@cli.command()
@click.option(
    "--src",
    default="https://json.commanderspellbook.com/variants.json",
    help="URL or path to variants.json source file.",
)
@click.option(
    "--outdir",
    default="data/spellbook",
    help="Output directory for spellbook artifacts.",
)
@click.option(
    "--enable/--disable",
    default=True,
    help="Master switch to enable/disable spellbook generation.",
)
@click.option(
    "--gzip-outputs",
    is_flag=True,
    default=False,
    help="Write gzip compressed output files.",
)
@click.option(
    "--split",
    is_flag=True,
    default=True,
    help="Split large files based on token limits.",
)
def build_spellbook(
    src: str, outdir: str, enable: bool, gzip_outputs: bool, split: bool
) -> None:
    """Download and process Commander Spellbook combo data."""
    from pathlib import Path

    from ccx.commands.build_spellbook import build_spellbook as run_build_spellbook

    run_build_spellbook(
        src=src,
        outdir=Path(outdir),
        enabled=enable,
        gzip_outputs=gzip_outputs,
        split=split,
    )


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
