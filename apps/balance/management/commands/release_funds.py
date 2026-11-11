from django.core.management.base import BaseCommand

from apps.balance.services import release_funds


class Command(BaseCommand):
    help = "Перевести удержанные деньги в доступные после HOLD_DAYS, если нет спора (раз в час)"

    def handle(self, *args, **options):
        self.stdout.write(f"Переведено в доступные начислений: {release_funds()}")
