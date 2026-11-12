// Корзина для статичного магазина: хранит товары в localStorage.
const STORAGE_KEY = 'shop_cart';

function formatPrice(value) {
  return value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ' ₽';
}

function addItem(product, quantity) {
  const items = loadCart();
  const existing = items.find(function (item) { return item.id === product.id; });
  if (existing) {
    existing.qty += quantity;
  } else {
    items.push({ id: product.id, title: product.title, price: product.price, qty: quantity });
  }
  saveCart(items);
  return items;
}

function loadCart() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    return [];
  }
}

function renderCart(container) {
  const items = loadCart();
  if (!items.length) {
    container.innerHTML = '<p class="cart-empty">Корзина пуста</p>';
    return;
  }
  const rows = items.map(function (item) {
    return '<li data-id="' + item.id + '">' + item.title + ' × ' + item.qty +
      ' <b>' + formatPrice(item.price * item.qty) + '</b>' +
      ' <button data-action="minus">−</button><button data-action="plus">+</button>' +
      ' <button data-action="remove">Удалить</button></li>';
  });
  container.innerHTML = '<ul>' + rows.join('') + '</ul><p>Итого: ' + formatPrice(cartTotal(items)) + '</p>';
}

function changeQuantity(id, delta) {
  const items = loadCart();
  for (let i = 0; i < items.length; i++) {
    if (items[i].id === id) {
      items[i].qty = Math.max(1, items[i].qty + delta);
    }
  }
  saveCart(items);
  return items;
}

function saveCart(items) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  document.dispatchEvent(new CustomEvent('cart:changed', { detail: items }));
}

function cartTotal(items, promo) {
  let sum = 0;
  items.forEach(function (item) { sum += item.price * item.qty; });
  if (promo && promo.percent) {
    sum = sum - Math.round(sum * promo.percent / 100);
  }
  return sum;
}

function removeItem(id) {
  const items = loadCart().filter(function (item) { return item.id !== id; });
  saveCart(items);
  return items;
}
