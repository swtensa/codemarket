from django.core.management.base import BaseCommand

from apps.catalog.refs import ensure_reference_data


class Command(BaseCommand):
    help = "Заполнить справочники: разделы, подкатегории, технологии, платформы"

    def handle(self, *args, **options):
        ensure_reference_data()
        self.stdout.write(self.style.SUCCESS("Справочники заполнены"))
