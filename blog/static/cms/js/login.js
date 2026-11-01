(() => {
  const form = document.querySelector("#login-form");
  const feedback = document.querySelector("#login-feedback");
  const submit = document.querySelector("#login-submit");
  if (!form || !feedback || !submit) return;

  const setFeedback = (message, type = "error") => {
    feedback.textContent = message;
    feedback.className = `mt-5 rounded-xl border px-4 py-3 text-sm font-semibold transition-all duration-300 ${type === "success" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-red-200 bg-red-50 text-red-700"}`;
    feedback.removeAttribute("hidden");
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    feedback.setAttribute("hidden", "");
    form.querySelectorAll("input").forEach((input) => input.removeAttribute("aria-invalid"));
    submit.disabled = true;
    submit.classList.add("opacity-70");
    submit.querySelector("span").textContent = "Проверяем…";

    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        form.querySelectorAll("input[type='text'], input[type='password']").forEach((input) => input.setAttribute("aria-invalid", "true"));
        setFeedback(payload.message || "Не удалось войти. Проверьте данные.");
        return;
      }
      setFeedback("Вход выполнен. Открываем управление статьями…", "success");
      submit.querySelector("span").textContent = "Готово";
      window.setTimeout(() => window.location.assign(payload.redirect), 280);
    } catch (_) {
      setFeedback("Сервер не ответил. Попробуйте ещё раз.");
    } finally {
      if (submit.querySelector("span").textContent !== "Готово") {
        submit.disabled = false;
        submit.classList.remove("opacity-70");
        submit.querySelector("span").textContent = "Войти";
      }
    }
  });
})();
