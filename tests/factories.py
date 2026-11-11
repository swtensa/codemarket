"""Фабрики тестовых данных (factory-boy)."""

import factory
from django.utils import timezone

from apps.accounts.models import User

PASSWORD = "testpass123"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@test.ru")
    username = factory.Sequence(lambda n: f"user{n}")
    terms_accepted_at = factory.LazyFunction(timezone.now)

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        self.set_password(extracted or PASSWORD)
        if create:
            self.save()
