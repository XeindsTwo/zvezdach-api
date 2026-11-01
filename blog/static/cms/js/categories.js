(() => {
  const modal = document.querySelector("#category-modal");
  const form = document.querySelector("#category-form");
  const grid = document.querySelector("#category-grid");
  if (!modal || !form || !grid) return;

  const fields = {
    nameRu: form.querySelector("[name='name_ru']"),
    nameEn: form.querySelector("[name='name_en']"),
    active: form.querySelector("[name='is_active']"),
  };
  const title = document.querySelector("#category-modal-title");
  const submit = document.querySelector("[data-category-submit]");
  const errors = document.querySelector("#category-form-errors");
  const empty = document.querySelector("#category-empty");
  const toast = document.querySelector("#category-toast");
  let closing = false;

  const closeModal = () => {
    if (!modal.open || closing) return;
    closing = true;
    modal.setAttribute("data-closing", "");
    window.setTimeout(() => {
      modal.close();
      modal.removeAttribute("data-closing");
      closing = false;
      clearErrors();
    }, 160);
  };

  const showToast = (message) => {
    toast.textContent = message;
    toast.classList.remove("translate-y-4", "opacity-0");
    window.setTimeout(() => toast.classList.add("translate-y-4", "opacity-0"), 2400);
  };
  const clearErrors = () => {
    errors.innerHTML = "";
    errors.classList.add("hidden");
    form.querySelectorAll("[aria-invalid='true']").forEach((input) => input.removeAttribute("aria-invalid"));
  };
  const showErrors = (payload) => {
    const labels = {name_ru:"Название на русском", name_en:"Название на английском", is_active:"Показывать на сайте", __all__:"Ошибка"};
    errors.innerHTML = "";
    Object.entries(payload || {}).forEach(([name, messages]) => {
      const paragraph = document.createElement("p");
      paragraph.textContent = `${labels[name] || name}: ${messages.join(" ")}`;
      errors.append(paragraph);
    });
    errors.classList.remove("hidden");
    Object.keys(payload || {}).forEach((name) => form.querySelector(`[name='${name}']`)?.setAttribute("aria-invalid", "true"));
  };
  const updateUrl = () => window.history.replaceState({}, "", window.location.pathname);
  const openCreate = () => {
    modal.removeAttribute("data-closing");
    form.reset();
    form.action = modal.dataset.createUrl;
    fields.active.checked = true;
    title.textContent = "Новая категория";
    clearErrors();
    modal.showModal();
    window.setTimeout(() => fields.nameRu.focus(), 80);
  };
  const openEdit = (card) => {
    modal.removeAttribute("data-closing");
    form.action = card.dataset.action;
    fields.nameRu.value = card.dataset.nameRu;
    fields.nameEn.value = card.dataset.nameEn;
    fields.active.checked = card.dataset.active === "true";
    title.textContent = `Изменить «${card.dataset.nameRu}»`;
    clearErrors();
    modal.showModal();
    window.setTimeout(() => fields.nameRu.focus(), 80);
  };

  const countText = (count) => `${count} ${count % 10 === 1 && count % 100 !== 11 ? "статья" : [2,3,4].includes(count % 10) && ![12,13,14].includes(count % 100) ? "статьи" : "статей"}`;
  const createCard = (data) => {
    const card = document.createElement("article");
    card.className = "group rounded-2xl border border-slate-200 bg-white p-5 transition hover:border-[#1db1ee]";
    card.setAttribute("data-category-card", "");
    card.innerHTML = `<div class="flex items-start justify-start gap-3"><span data-category-status class="rounded-full px-2.5 py-1 text-[11px] font-bold"></span></div><h2 data-category-name-ru class="mt-4 text-lg font-black text-slate-900"></h2><p data-category-name-en class="mt-2 text-sm font-semibold text-slate-500"></p><p data-category-name-id class="mt-1 text-sm text-slate-400"></p><div class="mt-5 flex items-center justify-between border-t border-slate-100 pt-4"><span data-category-count class="text-xs font-semibold text-slate-400"></span><button type="button" data-category-edit class="rounded-lg bg-slate-100 px-3 py-2 text-xs font-normal text-slate-700 transition-colors duration-300 ease-out group-hover:bg-[#092332] group-hover:text-white">Изменить</button></div>`;
    return card;
  };
  const fillCard = (card, data) => {
    Object.assign(card.dataset, {id:data.id, nameRu:data.name_ru, nameEn:data.name_en, active:String(data.is_active), action:`${modal.dataset.createUrl.replace(/new\/$/, `${data.id}/`)}`});
    card.querySelector("[data-category-name-ru]").textContent = data.name_ru;
    card.querySelector("[data-category-name-en]").textContent = data.name_en;
    card.querySelector("[data-category-count]").textContent = countText(data.article_count || 0);
    const status = card.querySelector("[data-category-status]");
    status.textContent = data.is_active ? "Показывается" : "Скрыта";
    status.className = `rounded-full px-2.5 py-1 text-[11px] font-bold ${data.is_active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`;
    card.querySelector("[data-category-edit]").onclick = () => openEdit(card);
  };
  const refreshEmptyState = () => {
    const total = grid.querySelectorAll("[data-category-card]").length;
    empty?.classList.toggle("hidden", total !== 0);
  };

  document.querySelector("[data-category-new]")?.addEventListener("click", openCreate);
  document.querySelectorAll("[data-category-close]").forEach((button) => button.addEventListener("click", closeModal));
  modal.addEventListener("click", (event) => { if (event.target === modal) closeModal(); });
  modal.addEventListener("cancel", (event) => { event.preventDefault(); closeModal(); });
  grid.querySelectorAll("[data-category-card]").forEach((card) => { card.querySelector("[data-category-edit]").onclick = () => openEdit(card); });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearErrors();
    submit.disabled = true;
    const original = submit.textContent;
    submit.textContent = "Сохраняем…";
    try {
      const response = await fetch(form.action, {method:"POST", headers:{"X-Requested-With":"XMLHttpRequest", Accept:"application/json"}, body:new FormData(form)});
      const payload = await response.json();
      if (!response.ok) { showErrors(payload.errors || {__all__:["Не удалось сохранить категорию."]}); return; }
      let card = grid.querySelector(`[data-category-card][data-id='${payload.id}']`);
      if (!card) { card = createCard(payload); grid.prepend(card); }
      fillCard(card, payload);
      refreshEmptyState();
      closeModal();
      showToast(payload.created ? "Категория добавлена" : "Категория обновлена");
    } catch (_) {
      showErrors({__all__:["Сервер не ответил. Проверьте соединение и попробуйте ещё раз."]});
    } finally {
      submit.disabled = false;
      submit.textContent = original;
    }
  });

  const params = new URLSearchParams(window.location.search);
  if (params.has("new")) { openCreate(); updateUrl(); }
  if (params.has("edit")) {
    const card = grid.querySelector(`[data-category-card][data-id='${params.get("edit")}']`);
    if (card) openEdit(card);
    updateUrl();
  }
  refreshEmptyState();
})();