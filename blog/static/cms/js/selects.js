(() => {
  const closeAll = (except) => {
    document.querySelectorAll("[data-select-menu]").forEach((menu) => {
      if (menu !== except) menu.classList.add("hidden");
    });
    document.querySelectorAll("[data-select-button]").forEach((button) => {
      if (button.nextElementSibling !== except) button.setAttribute("aria-expanded", "false");
      if (button.nextElementSibling !== except) button.lastElementChild?.classList.remove("rotate-180");
    });
  };

  document.querySelectorAll("select[data-custom-select]").forEach((select) => {
    const root = document.createElement("div");
    root.className = "relative w-full";
    select.parentNode.insertBefore(root, select);
    root.append(select);
    select.classList.add("sr-only");

    const button = document.createElement("button");
    button.type = "button";
    button.dataset.selectButton = "";
    button.className = "flex w-full items-center justify-between gap-3 rounded-2xl border border-stone-200 bg-white px-4 py-3 text-left text-sm text-stone-900 transition hover:border-stone-300 focus:border-[#1db1ee]";
    button.setAttribute("aria-haspopup", "listbox");
    button.setAttribute("aria-expanded", "false");

    const value = document.createElement("span");
    value.className = "min-w-0 truncate";
    const arrow = document.createElement("span");
    arrow.className = "text-xs text-slate-400 transition";
    arrow.textContent = "▼";
    button.append(value, arrow);

    const menu = document.createElement("div");
    menu.dataset.selectMenu = "";
    menu.setAttribute("role", "listbox");
    menu.className = "absolute left-0 right-0 z-40 mt-2 hidden max-h-64 overflow-y-auto rounded-2xl border border-slate-200 bg-white p-1.5";

    const sync = () => {
      value.textContent = select.selectedOptions[0]?.textContent || "Выберите значение";
      menu.querySelectorAll("[data-select-option]").forEach((option) => {
        const selected = option.dataset.value === select.value;
        option.setAttribute("aria-selected", String(selected));
        option.className = `mb-[3px] flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm font-semibold transition last:mb-0 ${selected ? "bg-[#fff1cf] text-[#7b4e00]" : "text-slate-600 hover:bg-slate-50"}`;
      });
    };
    [...select.options].forEach((nativeOption) => {
      const option = document.createElement("button");
      option.type = "button";
      option.dataset.selectOption = "";
      option.dataset.value = nativeOption.value;
      option.setAttribute("role", "option");
      option.textContent = nativeOption.textContent;
      option.disabled = nativeOption.disabled;
      option.addEventListener("click", () => {
        select.value = nativeOption.value;
        select.dispatchEvent(new Event("change", {bubbles: true}));
        sync();
        closeAll();
        button.focus();
      });
      menu.append(option);
    });
    root.append(button, menu);
    sync();

    const open = () => {
      if (select.disabled) return;
      const willOpen = menu.classList.contains("hidden");
      closeAll(willOpen ? menu : null);
      menu.classList.toggle("hidden", !willOpen);
      button.setAttribute("aria-expanded", String(willOpen));
      arrow.classList.toggle("rotate-180", willOpen);
      if (willOpen) menu.querySelector("[aria-selected='true']")?.focus();
    };
    button.addEventListener("click", open);
    button.addEventListener("keydown", (event) => {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) { event.preventDefault(); open(); }
    });
    menu.addEventListener("keydown", (event) => {
      const options = [...menu.querySelectorAll("[data-select-option]:not(:disabled)")];
      const index = options.indexOf(document.activeElement);
      if (event.key === "ArrowDown") { event.preventDefault(); options[(index + 1) % options.length]?.focus(); }
      if (event.key === "ArrowUp") { event.preventDefault(); options[(index - 1 + options.length) % options.length]?.focus(); }
      if (event.key === "Escape") { closeAll(); button.focus(); }
    });
    select.addEventListener("change", sync);
  });

  document.addEventListener("click", (event) => { if (!event.target.closest("[data-select-button], [data-select-menu]")) closeAll(); });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeAll(); });
})();
