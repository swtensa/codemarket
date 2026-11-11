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


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "catalog.Category"
        django_get_or_create = ["slug"]

    name = factory.Sequence(lambda n: f"Раздел {n}")
    slug = factory.Sequence(lambda n: f"section-{n}")


class SubcategoryFactory(CategoryFactory):
    parent = factory.SubFactory(CategoryFactory)
    name = factory.Sequence(lambda n: f"Подкатегория {n}")
    slug = factory.Sequence(lambda n: f"sub-{n}")


class TechnologyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "catalog.Technology"
        django_get_or_create = ["slug"]

    name = factory.Sequence(lambda n: f"Tech{n}")
    slug = factory.Sequence(lambda n: f"tech-{n}")


class PlatformFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "catalog.Platform"
        django_get_or_create = ["slug"]

    name = factory.Sequence(lambda n: f"Platform{n}")
    slug = factory.Sequence(lambda n: f"platform-{n}")


class SellerFactory(UserFactory):
    github_installation_id = factory.Sequence(lambda n: 1000 + n)
    seller_terms_accepted_at = factory.LazyFunction(timezone.now)


class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "catalog.Product"

    seller = factory.SubFactory(SellerFactory)
    category = factory.SubFactory(SubcategoryFactory)
    title = factory.Sequence(lambda n: f"Продукт {n}")
    slug = factory.Sequence(lambda n: f"product-{n}")
    short_description = "Краткое описание"
    description = "Полное описание продукта."
    price = 1000
    status = "published"
    published_at = factory.LazyFunction(timezone.now)
    source_repo_full_name = factory.LazyAttribute(lambda o: o.slug)
