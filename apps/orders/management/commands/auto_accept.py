from django.core.management.base import BaseCommand

from apps.orders.services import auto_accept


class Command(BaseCommand):
    help = "Принять сданные заказы без ответа покупателя дольше AUTO_ACCEPT_DAYS (если нет спора)"

    def handle(self, *args, **options):
        self.stdout.write(f"Принято автоматически: {auto_accept()}")
