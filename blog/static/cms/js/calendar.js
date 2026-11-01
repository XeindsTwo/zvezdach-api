(() => {
  const monthNames = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
  ];
  const weekDays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
  const pad = (value) => String(value).padStart(2, "0");
  const toIso = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  const fromIso = (value) => {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
    if (!match) return null;
    const parsed = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  };

  document.querySelectorAll("input[data-date-picker='true']").forEach((input) => {
    const wrapper = document.createElement("div");
    wrapper.className = "relative";
    input.parentNode.insertBefore(wrapper, input);
    wrapper.append(input);
    input.classList.add("cursor-pointer", "pr-11");
    input.setAttribute("aria-haspopup", "dialog");
    input.setAttribute("aria-expanded", "false");

    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "absolute right-0 top-0 grid h-full w-11 place-items-center text-slate-500 transition hover:text-[#007eaf]";
    trigger.setAttribute("aria-label", "Открыть календарь");
    trigger.innerHTML = '<svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="5" width="18" height="16" rx="3"/><path d="M8 3v4M16 3v4M3 10h18"/></svg>';
    wrapper.append(trigger);

    const panel = document.createElement("div");
    panel.className = "absolute left-0 right-0 z-50 mt-2 hidden min-w-[292px] rounded-2xl border border-slate-200 bg-white p-3 opacity-0 transition";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "Выбор даты публикации");
    panel.innerHTML = `
      <div class="flex items-center justify-between gap-3">
        <button type="button" data-calendar-prev class="grid size-10 place-items-center rounded-xl border border-slate-200 text-xl font-normal text-slate-600 transition hover:border-[#1db1ee]" aria-label="Предыдущий месяц">‹</button>
        <strong data-calendar-title class="text-sm font-semibold text-slate-800"></strong>
        <button type="button" data-calendar-next class="grid size-10 place-items-center rounded-xl border border-slate-200 text-xl font-normal text-slate-600 transition hover:border-[#1db1ee]" aria-label="Следующий месяц">›</button>
      </div>
      <div data-calendar-week class="mt-3 grid grid-cols-7 gap-1 text-center text-xs font-semibold text-slate-400"></div>
      <div data-calendar-days class="mt-1 grid grid-cols-7 gap-1"></div>
      <div class="mt-3 flex items-center justify-between border-t border-slate-100 pt-3">
        <button type="button" data-calendar-clear class="rounded-lg px-2 py-2 text-sm font-normal text-slate-500 transition hover:text-red-600">Очистить</button>
        <button type="button" data-calendar-today class="rounded-lg bg-[#e5f6fd] px-3 py-2 text-sm font-normal text-[#03658a] transition hover:bg-[#b9e7f8]">Сегодня</button>
      </div>`;
    wrapper.append(panel);

    const week = panel.querySelector("[data-calendar-week]");
    weekDays.forEach((label) => {
      const cell = document.createElement("span");
      cell.className = "py-1";
      cell.textContent = label;
      week.append(cell);
    });

    let visibleDate = fromIso(input.value) || new Date();
    visibleDate = new Date(visibleDate.getFullYear(), visibleDate.getMonth(), 1);
    let closeTimer;

    const render = () => {
      panel.querySelector("[data-calendar-title]").textContent = `${monthNames[visibleDate.getMonth()]} ${visibleDate.getFullYear()}`;
      const days = panel.querySelector("[data-calendar-days]");
      days.innerHTML = "";
      const firstWeekDay = (visibleDate.getDay() + 6) % 7;
      const daysInMonth = new Date(visibleDate.getFullYear(), visibleDate.getMonth() + 1, 0).getDate();
      const selected = input.value;
      const today = toIso(new Date());
      for (let blank = 0; blank < firstWeekDay; blank += 1) days.append(document.createElement("span"));
      for (let day = 1; day <= daysInMonth; day += 1) {
        const date = new Date(visibleDate.getFullYear(), visibleDate.getMonth(), day);
        const value = toIso(date);
        const button = document.createElement("button");
        button.type = "button";
        button.className = `grid aspect-square place-items-center rounded-lg text-sm font-normal transition ${value === selected ? "bg-[#092332] text-white" : value === today ? "bg-[#e5f6fd] text-[#03658a] hover:bg-[#b9e7f8]" : "text-slate-700 hover:bg-slate-100"}`;
        button.textContent = String(day);
        button.setAttribute("aria-label", value);
        if (value === selected) button.setAttribute("aria-current", "date");
        button.addEventListener("click", () => {
          input.value = value;
          input.dispatchEvent(new Event("input", {bubbles: true}));
          input.dispatchEvent(new Event("change", {bubbles: true}));
          close();
        });
        days.append(button);
      }
    };

    const open = () => {
      window.clearTimeout(closeTimer);
      const selected = fromIso(input.value);
      if (selected) visibleDate = new Date(selected.getFullYear(), selected.getMonth(), 1);
      render();
      panel.classList.remove("hidden");
      requestAnimationFrame(() => panel.classList.remove("opacity-0"));
      input.setAttribute("aria-expanded", "true");
    };
    const close = () => {
      panel.classList.add("opacity-0");
      input.setAttribute("aria-expanded", "false");
      closeTimer = window.setTimeout(() => panel.classList.add("hidden"), 150);
    };
    const toggle = () => panel.classList.contains("hidden") ? open() : close();

    input.addEventListener("click", toggle);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggle(); }
      if (event.key === "Escape") close();
    });
    trigger.addEventListener("click", toggle);
    panel.querySelector("[data-calendar-prev]").addEventListener("click", () => { visibleDate.setMonth(visibleDate.getMonth() - 1); render(); });
    panel.querySelector("[data-calendar-next]").addEventListener("click", () => { visibleDate.setMonth(visibleDate.getMonth() + 1); render(); });
    panel.querySelector("[data-calendar-today]").addEventListener("click", () => {
      const today = new Date();
      input.value = toIso(today);
      input.dispatchEvent(new Event("input", {bubbles: true}));
      input.dispatchEvent(new Event("change", {bubbles: true}));
      close();
    });
    panel.querySelector("[data-calendar-clear]").addEventListener("click", () => {
      input.value = "";
      input.dispatchEvent(new Event("input", {bubbles: true}));
      input.dispatchEvent(new Event("change", {bubbles: true}));
      close();
    });
    document.addEventListener("click", (event) => { if (!wrapper.contains(event.target)) close(); });
  });
})();
