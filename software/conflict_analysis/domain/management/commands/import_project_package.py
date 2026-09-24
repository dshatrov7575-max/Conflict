"""Import one validated project package atomically."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from domain.services.project_packages import ProjectPackageError, import_project_package


class Command(BaseCommand):
    help = "Validate and atomically import a conflict-analysis JSON project package."

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path)

    def handle(self, *args, **options):
        path: Path = options["path"]
        try:
            raw_json = path.read_text(encoding="utf-8")
            project = import_project_package(raw_json)
        except OSError as exc:
            raise CommandError(f"Cannot read {path}: {exc}.") from exc
        except ProjectPackageError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Imported {project.code} ({project.id})."))
