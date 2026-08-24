"""Preview or atomically commit one canonical Foundation package."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from domain.models import ProjectWorkspace
from domain.services.foundation_packages import (
    FoundationPackageError,
    attempt_foundation_import,
    preview_foundation_package,
)


class Command(BaseCommand):
    help = "Validate/preview a Foundation JSON/XLS adapter input and optionally commit atomically."

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path)
        parser.add_argument("--workspace", required=True, help="Exact target workspace UUID.")
        parser.add_argument("--adapter", default="json", help="Registered transport adapter.")
        parser.add_argument("--commit", action="store_true", help="Commit after a valid preview.")
        parser.add_argument("--actor", help="Required attributable actor when --commit is used.")
        parser.add_argument(
            "--allow-nonempty",
            action="store_true",
            help="Allow append-only insertion into a non-empty workspace; never overwrites.",
        )
        parser.add_argument(
            "--selected-input",
            default="{}",
            help="JSON object describing selected sheet/column input for the receipt.",
        )

    def handle(self, *args, **options):
        path: Path = options["path"]
        try:
            workspace_id = UUID(options["workspace"])
            workspace = ProjectWorkspace.objects.get(pk=workspace_id)
        except (ValueError, ProjectWorkspace.DoesNotExist) as exc:
            raise CommandError(f"Unknown workspace {options['workspace']!r}.") from exc
        if options["commit"] and not (options["actor"] or "").strip():
            raise CommandError("--actor is required with --commit.")
        try:
            selected_input = json.loads(options["selected_input"])
        except json.JSONDecodeError as exc:
            raise CommandError(f"--selected-input is invalid JSON: {exc.msg}.") from exc
        if not isinstance(selected_input, dict):
            raise CommandError("--selected-input must be a JSON object.")
        try:
            if options["commit"]:
                attempt = attempt_foundation_import(
                    path,
                    workspace=workspace,
                    adapter=options["adapter"],
                    selected_input=selected_input,
                    allow_nonempty=options["allow_nonempty"],
                    actor_identifier=options["actor"],
                )
                if attempt.status != "COMMITTED":
                    assert attempt.receipt is not None
                    messages = "; ".join(
                        error["message"] for error in attempt.report.errors
                    )
                    raise CommandError(
                        f"{attempt.status} receipt={attempt.receipt.code}: {messages}"
                    )
                assert attempt.receipt is not None
                self.stdout.write(
                    self.style.SUCCESS(
                        f"COMMIT PASS receipt={attempt.receipt.code} "
                        f"checksum={attempt.receipt.checksum}"
                    )
                )
                return
            preview = preview_foundation_package(
                path,
                workspace=workspace,
                adapter=options["adapter"],
                selected_input=selected_input,
                allow_nonempty=options["allow_nonempty"],
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"PREVIEW PASS checksum={preview.checksum} rows={sum(preview.counts.values())}"
                )
            )
            for warning in preview.warnings:
                self.stdout.write(self.style.WARNING(warning))
        except (FoundationPackageError, OSError) as exc:
            raise CommandError(str(exc)) from exc
