// Общие сценарии интерфейса CodeMarket.
(function () {
  // Toast-сообщения исчезают через 5 секунд.
  document.querySelectorAll('.cm-toast').forEach(function (el) {
    setTimeout(function () {
      el.style.transition = 'opacity .4s';
      el.style.opacity = '0';
      setTimeout(function () { el.remove(); }, 450);
    }, 5000);
  });

  // Кнопка отправки блокируется на время запроса.
  document.querySelectorAll('form').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (form.dataset.noLock !== undefined) return;
      var btn = e.submitter || form.querySelector('[type=submit]');
      if (btn && !btn.disabled) {
        setTimeout(function () { btn.disabled = true; }, 0);
        if (btn.name) {
          var h = document.createElement('input');
          h.type = 'hidden'; h.name = btn.name; h.value = btn.value;
          form.appendChild(h);
        }
      }
    });
  });

  // Подтверждение опасных действий в модальном окне.
  var modalEl = document.getElementById('cmConfirm');
  if (!modalEl) {
    modalEl = document.createElement('div');
    modalEl.className = 'modal fade'; modalEl.id = 'cmConfirm'; modalEl.tabIndex = -1;
    modalEl.innerHTML = '<div class="modal-dialog modal-dialog-centered"><div class="modal-content">' +
      '<div class="modal-header"><h5 class="modal-title"><i class="bi bi-exclamation-triangle text-danger me-2"></i>Подтвердите действие</h5>' +
      '<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Закрыть"></button></div>' +
      '<div class="modal-body"></div><div class="modal-footer">' +
      '<button type="button" class="btn btn-outline-primary" data-bs-dismiss="modal">Отмена</button>' +
      '<button type="button" class="btn btn-danger" data-cm-ok>Подтвердить</button></div></div></div>';
    document.body.appendChild(modalEl);
  }
  var pending = null;
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-confirm]');
    if (!btn || btn.dataset.confirmed) return;
    e.preventDefault();
    pending = btn;
    modalEl.querySelector('.modal-body').textContent = btn.dataset.confirm;
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  });
  modalEl.querySelector('[data-cm-ok]').addEventListener('click', function () {
    if (!pending) return;
    bootstrap.Modal.getOrCreateInstance(modalEl).hide();
    var form = pending.closest('form');
    if (form) {
      if (!form.reportValidity()) { pending = null; return; }
      if (pending.name) {
        var h = document.createElement('input');
        h.type = 'hidden'; h.name = pending.name; h.value = pending.value;
        form.appendChild(h);
      }
      form.submit();
    } else if (pending.href) {
      window.location = pending.href;
    }
    pending = null;
  });

  // Копирование текста в буфер.
  document.querySelectorAll('[data-copy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var text = document.querySelector(btn.dataset.copy).textContent.trim();
      navigator.clipboard.writeText(text).then(function () {
        var old = btn.innerHTML;
        btn.innerHTML = '<i class="bi bi-check2"></i> Скопировано';
        setTimeout(function () { btn.innerHTML = old; }, 1500);
      });
    });
  });
})();
