from django.core.management.base import BaseCommand

from apps.purchases.services import sync_access


class Command(BaseCommand):
    help = "Пригласить оплативших покупателей в репозитории-копии и обновить статусы приглашений"

    def handle(self, *args, **options):
        self.stdout.write(f"Отправлено приглашений: {sync_access()}")
