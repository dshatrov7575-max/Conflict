"""Export one project as deterministic, checksummed JSON."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from domain.models import Project
from domain.services.project_packages import export_project_json


class Command(BaseCommand):
    help = "Export a project to the versioned conflict-analysis JSON package format."

    def add_arguments(self, parser):
        parser.add_argument("project_code")
        parser.add_argument("path", type=Path)

    def handle(self, *args, **options):
        try:
            project = Project.objects.get(code=options["project_code"])
        except Project.DoesNotExist as exc:
            raise CommandError(f"Unknown project code {options['project_code']!r}.") from exc
        path: Path = options["path"]
        path.write_text(export_project_json(project), encoding="utf-8", newline="\n")
        self.stdout.write(self.style.SUCCESS(f"Exported {project.code} to {path}."))
