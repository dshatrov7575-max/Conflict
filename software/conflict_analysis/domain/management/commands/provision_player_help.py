"""Explicit provisioning of exact, immutable PLAYER Help and Workspace bindings."""

import json

from django.core.management.base import BaseCommand, CommandError

from domain.services.player_help_catalog import PlayerHelpCatalogError, provision_player_help


class Command(BaseCommand):
    help = "Provision the frozen G7 PLAYER Help catalog and existing Workspace bindings."

    def handle(self, *args, **options):
        try:
            result = provision_player_help()
        except PlayerHelpCatalogError as exc:
            raise CommandError("PLAYER_HELP_CATALOG_CONFLICT: provisioning rolled back.") from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
