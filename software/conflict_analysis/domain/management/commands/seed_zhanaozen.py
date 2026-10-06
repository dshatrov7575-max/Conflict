"""Install the versioned Zhanaozen demo project."""

from django.core.management.base import BaseCommand

from domain.models import GroupTensionRelation, ParticipantGroup, TensionPoint, TimeSlice
from domain.services.seed import seed_zhanaozen_demo


class Command(BaseCommand):
    help = "Create or refresh the idempotent KZ-ZHANAOZEN-DEMO-1.0 seed."

    def handle(self, *args, **options):
        project = seed_zhanaozen_demo()
        counts = {
            "time_slices": TimeSlice.objects.filter(project=project).count(),
            "tension_points": TensionPoint.objects.filter(project=project).count(),
            "participant_groups": ParticipantGroup.objects.filter(project=project).count(),
            "relations": GroupTensionRelation.objects.filter(project=project).count(),
        }
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {project.code} ({project.id}): "
                f"{counts['time_slices']} slices, {counts['tension_points']} PTN, "
                f"{counts['participant_groups']} GU, {counts['relations']} relations."
            )
        )
