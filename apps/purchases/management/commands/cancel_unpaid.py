from django.core.management.base import BaseCommand

from apps.purchases.services import cancel_unpaid


class Command(BaseCommand):
    help = "Отменить покупки, не оплаченные за PAYMENT_TIMEOUT_MIN минут"

    def handle(self, *args, **options):
        self.stdout.write(f"Отменено покупок: {cancel_unpaid()}")
