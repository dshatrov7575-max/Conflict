"""Export one workspace as deterministic canonical Foundation JSON."""

from pathlib import Path
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from domain.models import ProjectWorkspace
from domain.services.foundation_packages import export_foundation_json


class Command(BaseCommand):
    help = "Export one strict workspace as canonical Foundation JSON 2.0.0."

    def add_arguments(self, parser):
        parser.add_argument("workspace", help="Exact workspace UUID.")
        parser.add_argument("path", type=Path)

    def handle(self, *args, **options):
        try:
            workspace_id = UUID(options["workspace"])
            workspace = ProjectWorkspace.objects.get(pk=workspace_id)
        except (ValueError, ProjectWorkspace.DoesNotExist) as exc:
            raise CommandError(f"Unknown workspace {options['workspace']!r}.") from exc
        path: Path = options["path"]
        try:
            payload = export_foundation_json(workspace)
            path.write_text(payload, encoding="utf-8", newline="\n")
        except OSError as exc:
            raise CommandError(f"Cannot write {path}: {exc}.") from exc
        self.stdout.write(self.style.SUCCESS(f"Exported {workspace.code} to {path}."))
