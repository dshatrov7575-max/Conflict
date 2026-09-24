"""Provision the exact Foundation-owned Russian Studio Help catalog."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError, CommandParser

from domain.services.studio_help_catalog import (
    StudioHelpCatalogError,
    provision_studio_help,
)


class Command(BaseCommand):
    help = (
        "Atomically provision the pinned Russian Studio Help catalog from its "
        "explicit exact-byte JSON artifact."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "catalog_path",
            type=Path,
            help="Path to the exact committed studio_help_ru_v1.json bytes.",
        )

    def handle(self, *args, **options):
        try:
            result = provision_studio_help(options["catalog_path"])
        except StudioHelpCatalogError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"{result.catalog_id} {result.catalog_version} "
                f"sha256={result.source_sha256} "
                f"bytes={result.source_byte_length} "
                f"topics={result.topics_total} "
                f"topics_created={result.topics_created} "
                f"bindings={result.bindings_total} "
                f"bindings_created={result.bindings_created}"
            )
        )
