"""Провайдеры оплаты: интерфейс PaymentProvider, ЮKassa (тестовый магазин) и фейковый провайдер."""

import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings

log = logging.getLogger("codemarket")


class PaymentError(Exception):
    pass


@dataclass
class CreatedPayment:
    external_id: str
    confirmation_url: str
    status: str


class PaymentProvider:
    """Интерфейс провайдера оплаты."""

    name = "base"

    def create_payment(self, *, amount, description, idempotence_key, return_url, metadata) -> CreatedPayment:
        raise NotImplementedError

    def get_status(self, external_id) -> str:
        """Статус платежа у провайдера: pending / waiting_for_capture / succeeded / canceled."""
        raise NotImplementedError


class YooKassaProvider(PaymentProvider):
    """ЮKassa: confirmation.type=redirect, ключ идемпотентности, проверка статуса через Payment.find_one."""

    name = "yookassa"

    def __init__(self):
        if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
            raise PaymentError("ЮKassa не настроена: заполните YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY в .env")
        from yookassa import Configuration

        Configuration.configure(settings.yookassa_shop_id, settings.yookassa_secret_key)

    def create_payment(self, *, amount, description, idempotence_key, return_url, metadata):
        from yookassa import Payment as YkPayment

        try:
            p = YkPayment.create(
                {
                    "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
                    "confirmation": {"type": "redirect", "return_url": return_url},
                    "capture": True,
                    "description": description[:128],
                    "metadata": metadata,
                },
                idempotence_key,
            )
        except Exception as e:  # ошибки сети и API ЮKassa
            log.error("ЮKassa create_payment: %s", e)
            raise PaymentError("Платёжный сервис недоступен, попробуйте позже") from e
        return CreatedPayment(external_id=p.id, confirmation_url=p.confirmation.confirmation_url, status=p.status)

    def get_status(self, external_id):
        from yookassa import Payment as YkPayment

        try:
            return YkPayment.find_one(external_id).status
        except Exception as e:
            log.error("ЮKassa find_one %s: %s", external_id, e)
            raise PaymentError("Не удалось проверить платёж") from e


class FakeProvider(PaymentProvider):
    """Фейковый провайдер для разработки, тестов и демо.

    Состояние «у провайдера» хранится в файлах private/fake_payments/<id>.json,
    отдельно от таблицы Payment: так повторная проверка статуса работает так же, как с ЮKassa.
    """

    name = "fake"

    @property
    def root(self):
        d = Path(settings.storage_private) / "fake_payments"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _file(self, external_id):
        safe = "".join(c for c in external_id if c.isalnum() or c == "-")
        return self.root / f"{safe}.json"

    def create_payment(self, *, amount, description, idempotence_key, return_url, metadata):
        for f in self.root.glob("*.json"):  # идемпотентность: тот же ключ — тот же платёж
            data = json.loads(f.read_text(encoding="utf-8"))
            if data["idempotence_key"] == idempotence_key:
                return CreatedPayment(data["id"], data["confirmation_url"], data["status"])
        external_id = f"fake-{uuid.uuid4()}"
        url = f"/payments/fake/{external_id}/"
        data = {
            "id": external_id,
            "amount": str(amount),
            "description": description,
            "idempotence_key": idempotence_key,
            "status": "pending",
            "confirmation_url": url,
            "return_url": return_url,
            "metadata": metadata,
        }
        self._file(external_id).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return CreatedPayment(external_id, url, "pending")

    def get_status(self, external_id):
        f = self._file(external_id)
        if not f.exists():
            raise PaymentError("Платёж не найден у провайдера")
        return json.loads(f.read_text(encoding="utf-8"))["status"]

    def get(self, external_id):
        f = self._file(external_id)
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    def set_status(self, external_id, status):
        """Действие на странице-заглушке: «Оплатить» или «Отклонить»."""
        data = self.get(external_id)
        if data is None:
            raise PaymentError("Платёж не найден")
        if data["status"] == "pending":
            data["status"] = status
            self._file(external_id).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data


def get_provider():
    if settings.payment_provider == "yookassa":
        return YooKassaProvider()
    return FakeProvider()
