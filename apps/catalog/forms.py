from django import forms

from .models import PRODUCT_MAX_PRICE, PRODUCT_MIN_PRICE, Category, Platform, Product, Technology

CHECKS = forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"})


class GroupedCategoryField(forms.ModelChoiceField):
    """Выбор подкатегории, сгруппированной по разделам."""

    def __init__(self, **kwargs):
        super().__init__(queryset=Category.objects.filter(parent__isnull=False).select_related("parent"), **kwargs)

    @property
    def choices(self):
        groups = {}
        for c in self.queryset.order_by("parent__position", "position", "name"):
            groups.setdefault(c.parent.name, []).append((c.pk, c.name))
        return [("", "— выберите —"), *groups.items()]

    @choices.setter
    def choices(self, value):
        pass


class RepoStepForm(forms.Form):
    repo = forms.ChoiceField(label="Репозиторий", help_text="Репозитории, к которым установлено приложение CodeMarket.")
    accept_seller_terms = forms.BooleanField(
        label="Принимаю условия для продавцов",
        required=False,
    )

    def __init__(self, *args, repos=(), need_terms=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.repos = {r.full_name: r for r in repos}
        self.fields["repo"].choices = [("", "— выберите —")] + [(r.full_name, r.full_name) for r in repos]
        self.need_terms = need_terms
        if need_terms:
            self.fields["accept_seller_terms"].required = True
            self.fields["accept_seller_terms"].error_messages["required"] = "Без согласия создать продукт нельзя."
        else:
            del self.fields["accept_seller_terms"]


class InfoStepForm(forms.Form):
    title = forms.CharField(label="Название", max_length=120)
    short_description = forms.CharField(
        label="Краткое описание", max_length=200, widget=forms.Textarea(attrs={"rows": 2}), help_text="До 200 символов."
    )
    description = forms.CharField(
        label="Описание",
        widget=forms.Textarea(attrs={"rows": 8}),
        help_text="Что умеет продукт, как установить, что входит в комплект.",
    )
    price = forms.DecimalField(
        label="Цена, ₽",
        min_value=PRODUCT_MIN_PRICE,
        max_value=PRODUCT_MAX_PRICE,
        decimal_places=0,
        help_text=f"От {PRODUCT_MIN_PRICE} до {PRODUCT_MAX_PRICE:,} ₽".replace(",", " "),
    )


class CategoryStepForm(forms.Form):
    category = GroupedCategoryField(label="Подкатегория")
    technologies = forms.ModelMultipleChoiceField(
        label="Технологии", queryset=Technology.objects.all(), widget=CHECKS, required=False
    )
    platforms = forms.ModelMultipleChoiceField(
        label="Платформы", queryset=Platform.objects.all(), widget=CHECKS, required=False
    )
    demo_url = forms.URLField(label="Ссылка на демо", required=False, assume_scheme="https")


class ProductEditForm(forms.ModelForm):
    category = GroupedCategoryField(label="Подкатегория")

    class Meta:
        model = Product
        fields = [
            "title",
            "short_description",
            "description",
            "price",
            "category",
            "technologies",
            "platforms",
            "demo_url",
        ]
        widgets = {
            "short_description": forms.Textarea(attrs={"rows": 2}),
            "description": forms.Textarea(attrs={"rows": 8}),
            "technologies": CHECKS,
            "platforms": CHECKS,
        }


class ScreenshotsForm(forms.Form):
    images = forms.FileField(
        label="Скриншоты",
        help_text="До 8 штук, jpg, png или webp, до 3 МБ каждый.",
        widget=forms.ClearableFileInput(attrs={"allow_multiple_selected": True, "accept": ".jpg,.jpeg,.png,.webp"}),
    )
