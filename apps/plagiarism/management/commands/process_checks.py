from django.core.management.base import BaseCommand

from apps.plagiarism.services import process_pending


class Command(BaseCommand):
    help = "Проверить на заимствования версии в статусе «Проверяется» (запускается раз в минуту)"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10)

    def handle(self, *args, **options):
        n = process_pending(options["limit"])
        self.stdout.write(f"Проверено версий: {n}")
