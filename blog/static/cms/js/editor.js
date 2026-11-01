(() => {
  const csrf = () => document.cookie.split("; ").find((row) => row.startsWith("csrftoken="))?.split("=")[1] || "";
  const MAX_IMAGE_FILE_SIZE = 2 * 1024 * 1024;
  const MAX_GIF_FILE_SIZE = 5 * 1024 * 1024;
  const ALLOWED_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/avif", "image/gif"]);
  const ALLOWED_IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "webp", "avif", "gif"]);
  const imageFileError = (file) => {
    if (!file) return "Выберите файл изображения";
    const extension = String(file.name || "").split(".").pop().toLowerCase();
    const isGif = String(file.type || "").toLowerCase() === "image/gif" || extension === "gif";
    const sizeLimit = isGif ? MAX_GIF_FILE_SIZE : MAX_IMAGE_FILE_SIZE;
    if (file.size > sizeLimit) return `Файл «${file.name}» весит больше ${isGif ? "5" : "2"} МБ`;
    if (!ALLOWED_IMAGE_TYPES.has(String(file.type || "").toLowerCase()) && !ALLOWED_IMAGE_EXTENSIONS.has(extension)) {
      return `Формат файла «${file.name}» не поддерживается — разрешены PNG, JPG, JPEG, WebP, AVIF и GIF`;
    }
    return "";
  };
  const reportUploadError = (message) => document.dispatchEvent(new CustomEvent("cms-upload-error", {detail: {message}}));
  const youtubeVideoIdFromUrl = (value) => {
    try {
      const url = new URL(String(value || "").trim());
      const host = url.hostname.toLowerCase().replace(/^(www\.|m\.)/, "");
      let id = "";
      if (host === "youtu.be") id = url.pathname.split("/").filter(Boolean)[0] || "";
      if (host === "youtube.com" || host === "youtube-nocookie.com") {
        if (url.pathname === "/watch") id = url.searchParams.get("v") || "";
        else if (/^\/(embed|shorts|live)\//.test(url.pathname)) id = url.pathname.split("/").filter(Boolean)[1] || "";
      }
      return /^[A-Za-z0-9_-]{6,20}$/.test(id) ? id : "";
    } catch (_) {
      return "";
    }
  };
  const youtubeVideoIdFromIframe = (value) => {
    const code = String(value || "").trim();
    const iframe = code.match(/<iframe\b[^>]*\bsrc\s*=\s*(["'])(.*?)\1[^>]*>(?:\s*<\/iframe>)?/i);
    return iframe ? youtubeVideoIdFromUrl(iframe[2]) : "";
  };
  const storedGalleryNumbers = () => [...document.querySelectorAll("[data-gallery-form]")].flatMap((form) => {
    const id = form.querySelector("input[name$='-id']")?.value;
    const deleted = form.querySelector("input[name$='-DELETE']")?.checked;
    const number = Number(form.querySelector("input[name$='-gallery_number']")?.value || 0);
    return id && !deleted && number ? [number] : [];
  });
  const restoreMissingGalleryMarkers = (editor) => {
    const content = editor.getContent();
    const existing = new Set([...content.matchAll(/\[\[gallery(\d+)\]\]/gi)].map((match) => Number(match[1])));
    const missing = [...new Set(storedGalleryNumbers())].filter((number) => !existing.has(number));
    if (!missing.length) return;
    editor.setContent(`${content}${missing.map((number) => `<p data-gallery-marker="${number}">[[gallery${number}]]</p>`).join("")}`);
  };

  if (window.tinymce) {
    document.querySelectorAll("textarea[data-editor='tinymce']").forEach((textarea) => textarea.removeAttribute("required"));
    window.tinymce.init({
      selector: "textarea[data-editor='tinymce']",
      height: 680,
      license_key: "gpl",
      language: "ru",
      promotion: false,
      branding: false,
      placeholder: "Начните писать статью…",
      menubar: false,
      plugins: "anchor autolink charmap code fullscreen image link lists media preview searchreplace table visualblocks wordcount",
      invalid_styles: {"*": "text-align"},
      block_formats: "Обычный текст=p; Заголовок=h3",
      toolbar: "undo redo | blocks | bold italic underline | bullist numlist | link image youtubeEmbed table | articleGallery articleQuote code fullscreen",
      toolbar_sticky: true,
      image_caption: false,
      image_title: false,
      image_dimensions: false,
      a11y_advanced_options: false,
      media_live_embeds: false,
      automatic_uploads: true,
      file_picker_types: "image",
      relative_urls: false,
      remove_script_host: false,
      convert_urls: false,
      extended_valid_elements: "iframe[src|width|height|name|title|align|class|allow|allowfullscreen|frameborder|loading|referrerpolicy|sandbox|style],table[class|style|width|height|border|cellpadding|cellspacing],thead[class|style],tbody[class|style],tfoot[class|style],tr[class|style],th[class|style|scope|colspan|rowspan|width|height],td[class|style|colspan|rowspan|width|height],caption[class|style],col[class|style|span|width],colgroup[class|style|span|width],section[*],article[*],div[*],span[*]",
      invalid_elements: "script,object,embed,form,input,button,textarea,s,strike,del",
      valid_children: "+body[style|iframe],+p[iframe],+div[iframe],+section[iframe],+article[iframe]",
      setup: (editor) => {
        editor.on("init", () => {
          restoreMissingGalleryMarkers(editor);
          document.dispatchEvent(new CustomEvent("cms-editor-ready", {detail: {editor}}));
          const markers = [...editor.getContent().matchAll(/\[\[gallery(\d+)\]\]/gi)].map((match) => Number(match[1]));
          [...new Set(markers)].forEach((number) => document.dispatchEvent(new CustomEvent("cms-gallery-create", {detail: {number, reveal: false}})));
        });
        editor.on("change input undo redo", () => document.dispatchEvent(new CustomEvent("cms-editor-change")));
        editor.on("keydown", (event) => {
          if (event.key !== "Enter" || event.shiftKey || event.isComposing || !editor.dom.getParent(editor.selection.getNode(), "h3")) return;
          window.setTimeout(() => {
            if (editor.dom.getParent(editor.selection.getNode(), "h3")) editor.execCommand("FormatBlock", false, "p");
          }, 0);
        });
        editor.ui.registry.addButton("articleGallery", {
          text: "Галерея",
          tooltip: "Вставить галерею статьи в это место",
          onAction: () => {
            editor.selection.collapse(false);
            const numbers = [
              ...[...editor.getContent().matchAll(/\[\[gallery(\d+)\]\]/gi)].map((match) => Number(match[1])),
              ...[...document.querySelectorAll("[data-gallery-group]")].map((group) => Number(group.dataset.galleryNumber || 0)),
            ].filter(Boolean);
            const used = new Set(numbers);
            const number = Array.from({length: 10}, (_, index) => index + 1).find((candidate) => !used.has(candidate));
            if (!number) {
              editor.notificationManager.open({text: "В одной статье можно разместить до 10 галерей", type: "warning", timeout: 2400});
              return;
            }
            editor.insertContent(`<p data-gallery-marker="${number}">[[gallery${number}]]</p>`);
            document.dispatchEvent(new CustomEvent("cms-gallery-create", {detail: {number, reveal: true}}));
          },
        });
        editor.ui.registry.addButton("youtubeEmbed", {
          text: "YouTube",
          tooltip: "Вставить видео YouTube",
          onAction: () => {
            const bookmark = editor.selection.getBookmark(2, true);
            editor.windowManager.open({
            title: "Видео YouTube",
            body: {type: "panel", items: [{type: "textarea", name: "code", label: "Код iframe"}]},
            buttons: [{type: "cancel", text: "Отмена"}, {type: "submit", text: "Вставить видео", primary: true}],
            initialData: {code: ""},
            onSubmit: (dialog) => {
              const id = youtubeVideoIdFromIframe(dialog.getData().code);
              if (!id) {
                editor.notificationManager.open({text: "Вставьте корректный iframe-код YouTube", type: "warning", timeout: 2400});
                return;
              }
              editor.selection.moveToBookmark(bookmark);
              editor.selection.collapse(false);
              const src = `https://www.youtube-nocookie.com/embed/${id}`;
              editor.insertContent(`<iframe src="${src}" title="Видео YouTube" loading="lazy" width="560" height="315" frameborder="0" referrerpolicy="strict-origin-when-cross-origin" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>`);
              dialog.close();
            },
            });
          },
        });
        editor.ui.registry.addButton("articleQuote", {
          icon: "quote",
          tooltip: "Вставить цитату с автором",
          onAction: () => editor.windowManager.open({
            title: "Цитата",
            body: {
              type: "panel",
              items: [
                {type: "textarea", name: "text", label: "Текст цитаты"},
                {type: "input", name: "author", label: "Автор цитаты"},
              ],
            },
            buttons: [
              {type: "cancel", text: "Отмена"},
              {type: "submit", text: "Вставить цитату", primary: true},
            ],
            initialData: {text: "", author: ""},
            onSubmit: (dialog) => {
              const data = dialog.getData();
              const quote = String(data.text || "").trim();
              const author = String(data.author || "").trim();
              if (!quote || !author) {
                editor.notificationManager.open({text: "Укажите текст цитаты и автора", type: "warning", timeout: 2200});
                return;
              }
              const encode = (value) => String(value).replace(/[&<>"']/g, (character) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"})[character]).replace(/\r?\n/g, "<br>");
              editor.insertContent(`<blockquote><p>${encode(quote)}</p><cite>${encode(author)}</cite></blockquote><p></p>`);
              dialog.close();
            },
          }),
        });
      },
      content_style: "body{font-family:'SF Pro Display',Inter,system-ui,sans-serif;font-size:17px;line-height:1.75;margin:0;padding:24px;color:#1d2023}.mce-content-body[data-mce-placeholder]:not(.mce-visualblocks)::before{left:24px!important;top:24px!important}p{margin:0 0 18px;text-indent:0}p[data-gallery-marker]{display:inline-block;margin:12px 0;padding:7px 11px;border-radius:9px;background:#e5f6fd;color:#03658a;font-family:ui-monospace,monospace;font-size:14px;font-weight:600}h3{margin:32px 0 18px;font-size:21px;line-height:1.05}ol{list-style-type:decimal}img{max-width:100%;height:auto;border-radius:20px}iframe{display:block;width:560px;max-width:100%;aspect-ratio:16/9;height:auto;border:0;border-radius:20px;margin:18px 0}table{width:100%;margin:18px 0 28px;overflow:hidden;border:1px solid rgba(0,65,94,.2);border-radius:10px;border-collapse:separate;border-spacing:0}caption{margin-bottom:10px;font-weight:600;text-align:left}th,td{border:0;border-right:1px solid rgba(0,65,94,.2);border-bottom:1px solid rgba(0,65,94,.2);padding:10px 12px;vertical-align:top;text-align:left}th{background:#e5f6fd;font-weight:600}tr>*:last-child{border-right:0}table>:last-child>tr:last-child>*{border-bottom:0}blockquote{border-left:4px solid #1db1ee;margin:28px 0;padding:4px 0 4px 20px;color:#596973}blockquote p{margin:0;font-size:20px;font-weight:600;line-height:1.35}blockquote cite{display:block;margin-top:12px;font-size:14px;font-style:normal;color:#7c8c96}",
      images_upload_handler: (blobInfo) => new Promise((resolve, reject) => {
        const blob = blobInfo.blob();
        const uploadError = imageFileError(new File([blob], blobInfo.filename(), {type: blob.type}));
        if (uploadError) {
          reportUploadError(uploadError);
          reject(uploadError);
          return;
        }
        const body = new FormData();
        body.append("file", blob, blobInfo.filename());
        fetch(window.CMS_CONFIG.uploadUrl, {method: "POST", headers: {"X-CSRFToken": csrf()}, body})
          .then(async (response) => {
            const payload = await response.json();
            if (!response.ok || !payload.location) throw new Error(payload.error || "Не удалось загрузить файл");
            resolve(payload.location);
          })
          .catch((error) => reject(error.message));
      }),
    });
  }

  const root = document.querySelector("#tag-editor");
  if (!root) return;
  const hidden = document.querySelector("#id_tags_input");
  const query = document.querySelector("#tag-query");
  const chips = document.querySelector("#tag-chips");
  const results = document.querySelector("#tag-results");
  const localeInput = document.querySelector("#id_locale");
  let tags = [];
  try { tags = JSON.parse(hidden.value || "[]"); } catch (_) { tags = []; }

  const sync = () => {
    hidden.value = JSON.stringify(tags);
    chips.innerHTML = "";
    tags.forEach((name) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "rounded-full bg-sky-100 px-3 py-1.5 text-xs font-bold text-sky-900";
      chip.textContent = `#${name} ×`;
      chip.addEventListener("click", () => { tags = tags.filter((item) => item !== name); sync(); hidden.dispatchEvent(new Event("change", {bubbles: true})); });
      chips.append(chip);
    });
  };
  const add = (name) => {
    const clean = name.trim().slice(0, 80);
    if (clean && !tags.some((item) => item.toLowerCase() === clean.toLowerCase())) tags.push(clean);
    query.value = "";
    results.classList.add("hidden");
    sync();
    hidden.dispatchEvent(new Event("change", {bubbles: true}));
  };
  let timer;
  query.addEventListener("input", () => {
    clearTimeout(timer);
    const value = query.value.trim();
    if (value.length < 3) { results.classList.add("hidden"); return; }
    timer = setTimeout(async () => {
      const response = await fetch(`${root.dataset.searchUrl}?q=${encodeURIComponent(value)}&locale=${encodeURIComponent(localeInput?.value || "")}`);
      const payload = await response.json();
      results.innerHTML = "";
      payload.results.forEach((tag) => {
        const option = document.createElement("button");
        option.type = "button";
        option.className = "block w-full px-4 py-2.5 text-left text-sm hover:bg-sky-50";
        option.textContent = `#${tag.name}`;
        option.addEventListener("click", () => add(tag.name));
        results.append(option);
      });
      results.classList.toggle("hidden", payload.results.length === 0);
    }, 220);
  });
  query.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && query.value.trim()) { event.preventDefault(); add(query.value); }
    if (event.key === ",") { event.preventDefault(); add(query.value); }
  });
  sync();
  const keywordsField = document.querySelector("#meta-keywords-field");
  const toggleKeywords = () => keywordsField?.classList.toggle("hidden", localeInput?.value !== "ru");
  let tagLocale = localeInput?.value || "";
  localeInput?.addEventListener("change", () => {
    toggleKeywords();
    if (tagLocale && localeInput.value !== tagLocale) {
      tags = [];
      sync();
      query.value = "";
      results.replaceChildren();
      results.classList.add("hidden");
      hidden.dispatchEvent(new Event("change", {bubbles: true}));
    }
    tagLocale = localeInput.value;
  });
  toggleKeywords();

  const galleryRoot = document.querySelector("#gallery-forms");
  const galleryGroups = document.querySelector("#gallery-groups");
  const galleryTemplate = document.querySelector("#gallery-empty-form");
  const galleryGroupTemplate = document.querySelector("#gallery-group-template");
  const galleryTotal = document.querySelector("#id_gallery-TOTAL_FORMS");
  const galleryCaptionsInput = document.querySelector("#id_gallery_captions");
  if (!galleryRoot || !galleryGroups || !galleryTemplate || !galleryGroupTemplate || !galleryTotal || !galleryCaptionsInput) return;

  const groups = new Map();
  let galleryCaptions = {};
  try { galleryCaptions = JSON.parse(galleryCaptionsInput.value || "{}"); } catch (_) { galleryCaptions = {}; }
  const syncGalleryCaptions = () => { galleryCaptionsInput.value = JSON.stringify(galleryCaptions); };
  const activeGalleryForms = (group) => [...group.querySelectorAll("[data-gallery-form]")].filter((item) => !item.classList.contains("hidden"));
  const refreshGroup = (group) => {
    const number = Number(group.dataset.galleryNumber);
    const active = activeGalleryForms(group);
    active.forEach((item, index) => {
      const galleryNumber = item.querySelector("input[name$='-gallery_number']");
      const order = item.querySelector("input[name$='-sort_order']");
      if (galleryNumber) galleryNumber.value = String(number);
      if (order) order.value = String(index);
    });
    group.querySelector("[data-gallery-count]").textContent = String(active.length);
    group.querySelector("[data-gallery-empty]").classList.toggle("hidden", active.length > 0);
    const add = group.querySelector("[data-gallery-add]");
    add.disabled = active.length >= 5;
    add.classList.toggle("opacity-40", active.length >= 5);
  };
  const ensureGroup = (number) => {
    if (groups.has(number)) return groups.get(number);
    const wrapper = document.createElement("div");
    wrapper.innerHTML = galleryGroupTemplate.innerHTML.trim();
    const group = wrapper.firstElementChild;
    if (!group) return null;
    group.dataset.galleryNumber = String(number);
    group.querySelector("[data-gallery-title]").textContent = `Галерея №${number}`;
    group.querySelector("[data-gallery-marker]").textContent = `[[gallery${number}]]`;
    const caption = group.querySelector("[data-gallery-caption]");
    caption.value = galleryCaptions[String(number)] || "";
    caption.addEventListener("input", () => {
      const value = caption.value.trim();
      if (value) galleryCaptions[String(number)] = value;
      else delete galleryCaptions[String(number)];
      syncGalleryCaptions();
    });
    group.querySelector("[data-gallery-add]").addEventListener("click", () => addGalleryImage(number));
    group.querySelector("[data-gallery-remove]").addEventListener("click", () => removeGallery(number));
    groups.set(number, group);
    galleryGroups.append(group);
    refreshGroup(group);
    return group;
  };
  const bindGalleryRemove = (container) => {
    const file = container.querySelector("input[type='file']");
    const preview = container.querySelector("[data-gallery-image-preview]");
    const placeholder = container.querySelector("[data-gallery-image-placeholder]");
    container.querySelector("[data-gallery-image-trigger]")?.addEventListener("click", () => file?.click());
    file?.addEventListener("change", () => {
      const selected = file.files?.[0];
      if (!selected || !preview || !placeholder) return;
      const uploadError = imageFileError(selected);
      if (uploadError) {
        file.value = "";
        reportUploadError(uploadError);
        return;
      }
      preview.src = URL.createObjectURL(selected);
      preview.classList.remove("hidden");
      placeholder.classList.add("hidden");
    });
    container.querySelector(".remove-gallery-form")?.addEventListener("click", () => {
      const remove = container.querySelector("input[name$='-DELETE']");
      if (remove) remove.checked = true;
      container.classList.add("hidden");
      const group = container.closest("[data-gallery-group]");
      if (group) refreshGroup(group);
    });
  };
  const removeGallery = (number) => {
    const group = groups.get(number);
    if (!group || !window.confirm(`Убрать галерею №${number} и все её изображения?`)) return;
    group.querySelectorAll("[data-gallery-form]").forEach((form) => {
      const remove = form.querySelector("input[name$='-DELETE']");
      if (remove) remove.checked = true;
      form.classList.add("hidden");
      galleryRoot.append(form);
    });
    delete galleryCaptions[String(number)];
    syncGalleryCaptions();
    groups.delete(number);
    group.remove();
    const editor = window.tinymce?.get("id_content");
    if (editor) {
      const marker = new RegExp(`(?:<p[^>]*>\\s*)?\\[\\[gallery${number}\\]\\](?:\\s*<\\/p>)?`, "gi");
      editor.setContent(editor.getContent().replace(marker, ""));
      editor.fire("change");
    }
  };
  const addGalleryImage = (number) => {
    const group = ensureGroup(number);
    if (!group || activeGalleryForms(group).length >= 5) return;
    const index = Number(galleryTotal.value);
    const wrapper = document.createElement("div");
    wrapper.innerHTML = galleryTemplate.innerHTML.replaceAll("__prefix__", String(index)).trim();
    const next = wrapper.firstElementChild;
    if (!next) return;
    next.dataset.galleryNumber = String(number);
    const galleryNumber = next.querySelector("input[name$='-gallery_number']");
    if (galleryNumber) galleryNumber.value = String(number);
    group.querySelector("[data-gallery-images]").append(next);
    galleryTotal.value = String(index + 1);
    bindGalleryRemove(next);
    refreshGroup(group);
  };
  [...galleryRoot.querySelectorAll("[data-gallery-form]")]
    .sort((left, right) => Number(left.dataset.galleryNumber || 1) - Number(right.dataset.galleryNumber || 1))
    .forEach((form) => {
      const number = Number(form.dataset.galleryNumber || 1);
      const group = ensureGroup(number);
      group?.querySelector("[data-gallery-images]").append(form);
      bindGalleryRemove(form);
      if (group) refreshGroup(group);
    });
  document.addEventListener("cms-gallery-create", (event) => {
    const number = Number(event.detail?.number || 1);
    const group = ensureGroup(number);
    const editorIsFullscreen = document.body.classList.contains("tox-fullscreen") || document.documentElement.classList.contains("tox-fullscreen");
    if (event.detail?.reveal && !editorIsFullscreen) group?.scrollIntoView({behavior: "smooth", block: "center"});
  });
  document.querySelector("#article-form")?.addEventListener("submit", () => groups.forEach(refreshGroup));
  syncGalleryCaptions();

  const articleForm = document.querySelector("#article-form");
  if (!articleForm) return;
  const restoreBanner = document.querySelector("#draft-restore");
  const restoreButton = document.querySelector("#draft-restore-button");
  const discardButton = document.querySelector("#draft-discard");
  const validationBox = document.querySelector("#client-validation-errors");
  const trackedNames = ["locale", "category", "title", "slug", "excerpt", "cover_alt", "status", "editorial_status", "published_at", "seo_title", "seo_description", "meta_keywords", "gallery_captions"];
  const coverInput = articleForm.elements.namedItem("cover_image");
  const coverClear = articleForm.elements.namedItem("cover_image-clear");
  const coverPreview = document.querySelector("#cover-preview");
  const coverPreviewImage = document.querySelector("#cover-preview-image");
  const coverPreviewPlaceholder = document.querySelector("#cover-preview-placeholder");
  let mainEditor = null;
  let initialized = false;
  let dirty = false;
  let submitting = false;
  let initialSnapshot = "";
  let autosaveTimer = null;
  let coverPreviewUrl = "";

  const toastRoot = document.createElement("div");
  toastRoot.id = "cms-toast-root";
  toastRoot.className = "pointer-events-none fixed right-5 bottom-5 z-50 flex w-[calc(100%-2rem)] max-w-md flex-col gap-3";
  toastRoot.setAttribute("aria-live", "assertive");
  document.body.append(toastRoot);

  const normalizeMessage = (message) => String(message || "").trim().replace(/[.!?]+$/u, "");
  const showErrorToast = (errors, title = "Не удалось опубликовать") => {
    toastRoot.replaceChildren();
    const toast = document.createElement("div");
    toast.className = "pointer-events-auto translate-y-4 rounded-2xl border border-red-500/25 bg-[#3a1212] p-4 text-white opacity-0 transition-all duration-300";
    const cleanErrors = errors.map(normalizeMessage).filter(Boolean);
    toast.innerHTML = `<div class="flex items-start gap-3"><span class="grid size-10 shrink-0 place-items-center rounded-full bg-red-500/15 text-red-300"><svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 8v5m0 4h.01"/><path d="M10.3 3.6 2.7 17a2 2 0 0 0 1.7 3h15.2a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0Z"/></svg></span><div class="min-w-0 flex-1"><strong class="block text-sm font-semibold">${escapeHtml(normalizeMessage(title))}</strong><ul class="mt-2 space-y-1 text-sm text-red-100">${cleanErrors.slice(0, 5).map((error) => `<li>• ${escapeHtml(error)}</li>`).join("")}</ul>${cleanErrors.length > 5 ? `<p class="mt-2 text-sm text-red-300">И ещё ${cleanErrors.length - 5}</p>` : ""}</div><button type="button" class="grid size-8 shrink-0 place-items-center rounded-lg text-red-200 transition-colors hover:bg-red-500/15" aria-label="Закрыть уведомление">×</button></div>`;
    const close = () => {
      toast.classList.add("translate-y-4", "opacity-0");
      window.setTimeout(() => toast.remove(), 300);
    };
    toast.querySelector("button")?.addEventListener("click", close);
    toastRoot.append(toast);
    requestAnimationFrame(() => toast.classList.remove("translate-y-4", "opacity-0"));
    window.setTimeout(close, 8000);
  };
  const showSuccessToast = (message) => {
    toastRoot.replaceChildren();
    const toast = document.createElement("div");
    toast.className = "pointer-events-auto translate-y-4 rounded-2xl border border-emerald-500/25 bg-[#123526] p-4 text-white opacity-0 transition-all duration-300";
    toast.innerHTML = `<div class="flex items-center gap-3"><span class="grid size-10 shrink-0 place-items-center rounded-full bg-emerald-500/15 text-emerald-200"><svg viewBox="0 0 24 24" class="size-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 4 4L19 6"/></svg></span><strong class="min-w-0 flex-1 text-sm font-semibold">${escapeHtml(normalizeMessage(message))}</strong><button type="button" class="grid size-8 shrink-0 place-items-center rounded-lg text-emerald-100 transition-colors hover:bg-emerald-500/15" aria-label="Закрыть уведомление">×</button></div>`;
    const close = () => {
      toast.classList.add("translate-y-4", "opacity-0");
      window.setTimeout(() => toast.remove(), 300);
    };
    toast.querySelector("button")?.addEventListener("click", close);
    toastRoot.append(toast);
    requestAnimationFrame(() => toast.classList.remove("translate-y-4", "opacity-0"));
    window.setTimeout(close, 5000);
  };
  document.addEventListener("cms-upload-error", (event) => showErrorToast([event.detail?.message || "Не удалось выбрать изображение"]));

  const field = (name) => articleForm.elements.namedItem(name);
  const slugInput = field("slug");
  const titleInput = field("title");
  const editorialStatusInput = field("editorial_status");
  const primaryActionButton = document.querySelector("#publish-button");
  const primaryActionLabel = document.querySelector("#publish-button-label");
  const syncPrimaryAction = () => {
    if (!primaryActionButton || !primaryActionLabel) return;
    const isDraft = editorialStatusInput?.value === "draft";
    primaryActionButton.value = isDraft ? "save" : "publish";
    primaryActionLabel.textContent = isDraft ? "Сохранить изменения" : primaryActionButton.dataset.publishLabel;
  };
  editorialStatusInput?.addEventListener("change", syncPrimaryAction);
  let slugWasEdited = Boolean(slugInput?.value.trim());
  const slugMap = {"а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z","и":"i","й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f","х":"h","ц":"ts","ч":"ch","ш":"sh","щ":"sch","ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya"};
  const slugifyTitle = (value) => String(value || "").toLowerCase().split("").map((character) => slugMap[character] ?? character).join("").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").replace(/-+/g, "-").slice(0, 220);
  slugInput?.addEventListener("input", () => { slugWasEdited = Boolean(slugInput.value.trim()); });
  titleInput?.addEventListener("input", () => {
    if (!slugWasEdited && slugInput) slugInput.value = slugifyTitle(titleInput.value);
  });
  const editorContent = () => mainEditor ? mainEditor.getContent() : (field("content")?.value || "");
  const draftPayload = () => ({
    savedAt: new Date().toISOString(),
    fields: Object.fromEntries(trackedNames.map((name) => [name, field(name)?.value || ""])),
    content: editorContent(),
  });
  const selectedFiles = () => [...articleForm.querySelectorAll("input[type='file']")].flatMap((input) => [...input.files].map((file) => `${input.name}:${file.name}:${file.size}:${file.lastModified}`));
  const snapshot = () => JSON.stringify({fields: draftPayload().fields, content: editorContent(), tags: hidden.value, files:selectedFiles()});
  const safeStorage = {
    get: () => { try { return JSON.parse(localStorage.getItem(articleForm.dataset.draftKey) || "null"); } catch (_) { return null; } },
    set: (payload) => { try { localStorage.setItem(articleForm.dataset.draftKey, JSON.stringify(payload)); return true; } catch (_) { return false; } },
    remove: () => { try { localStorage.removeItem(articleForm.dataset.draftKey); } catch (_) {} },
  };
  const saveLocalDraft = () => {
    if (!dirty) return;
    safeStorage.set(draftPayload());
  };
  const queueAutosave = () => {
    window.clearTimeout(autosaveTimer);
    autosaveTimer = window.setTimeout(saveLocalDraft, 900);
  };
  const updateCounters = () => {
    document.querySelectorAll("[data-counter-for]").forEach((counter) => {
      const input = document.getElementById(counter.dataset.counterFor);
      const length = input?.value.length || 0;
      const limit = Number(counter.dataset.limit);
      counter.textContent = `${length} / ${limit}`;
      counter.classList.toggle("text-red-500", length > limit || (limit <= 170 && length > Math.round(limit * .95)));
      counter.classList.toggle("text-slate-400", length <= Math.round(limit * .95));
    });
  };
  const hasCover = () => !field("cover_image-clear")?.checked && (articleForm.dataset.existingCover === "true" || Boolean(field("cover_image")?.files?.length));
  const updateCoverPreview = () => {
    if (!coverPreviewImage || !coverPreviewPlaceholder) return;
    if (coverPreviewUrl.startsWith("blob:")) URL.revokeObjectURL(coverPreviewUrl);
    const file = coverInput?.files?.[0];
    coverPreviewUrl = file ? URL.createObjectURL(file) : (!coverClear?.checked ? articleForm.dataset.existingCoverUrl : "");
    if (coverPreviewUrl) {
      coverPreviewImage.src = coverPreviewUrl;
      coverPreviewImage.classList.remove("hidden");
      coverPreviewPlaceholder.classList.add("hidden");
    } else {
      coverPreviewImage.removeAttribute("src");
      coverPreviewImage.classList.add("hidden");
      coverPreviewPlaceholder.classList.remove("hidden");
    }
  };
  const readinessState = () => ({
    content: Boolean(field("title")?.value.trim() && editorContent().replace(/<[^>]*>/g, " ").trim().length >= 20),
    cover: Boolean(hasCover() && field("title")?.value.trim()),
    category: Boolean(field("category")?.value),
    excerpt: Boolean(field("excerpt")?.value.trim()),
    seo: Boolean(field("seo_title")?.value.trim() && field("seo_description")?.value.trim()),
    date: true,
  });
  const updateReadiness = () => {
    const state = readinessState();
    const ready = Object.values(state).filter(Boolean).length;
    const percent = Math.round(ready / Object.keys(state).length * 100);
    document.querySelector("#readiness-label").textContent = `${ready} из 6`;
    document.querySelector("#readiness-percent").textContent = `${percent}%`;
    document.querySelector("#readiness-progress").style.width = `${percent}%`;
    Object.entries(state).forEach(([name, complete]) => {
      const item = document.querySelector(`[data-ready-item='${name}']`);
      item.classList.toggle("text-white", complete);
      item.classList.toggle("text-stone-400", !complete);
      const icon = item.querySelector("i");
      icon.classList.toggle("bg-emerald-500", complete);
      icon.classList.toggle("bg-white/8", !complete);
    });
  };
  const escapeHtml = (value) => String(value || "").replace(/[&<>'"]/g, (character) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", "'":"&#39;", '"':"&quot;"})[character]);
  const onChange = () => {
    if (!initialized) return;
    dirty = snapshot() !== initialSnapshot;
    if (dirty) queueAutosave();
    updateCounters();
    updateReadiness();
  };
  const restoreDraft = (draft) => {
    Object.entries(draft.fields || {}).forEach(([name, value]) => { if (field(name)) field(name).value = value; });
    if (mainEditor) mainEditor.setContent(draft.content || ""); else if (field("content")) field("content").value = draft.content || "";
    syncPrimaryAction();
    restoreBanner.classList.add("hidden");
    restoreBanner.classList.remove("flex");
    onChange();
  };
  const initialize = () => {
    if (initialized) return;
    mainEditor = window.tinymce?.get("id_content") || mainEditor;
    initialSnapshot = snapshot();
    initialized = true;
    updateCounters();
    updateReadiness();
    updateCoverPreview();
    syncPrimaryAction();
    const draft = safeStorage.get();
    if (draft && JSON.stringify({fields:draft.fields, content:draft.content, tags:hidden.value, files:[]}) !== initialSnapshot) {
      restoreBanner.classList.remove("hidden");
      restoreBanner.classList.add("flex");
      restoreButton.onclick = () => restoreDraft(draft);
      discardButton.onclick = () => { safeStorage.remove(); restoreBanner.classList.add("hidden"); restoreBanner.classList.remove("flex"); };
    }
  };
  const publicationErrors = () => {
    if (field("status")?.value !== "published") return [];
    const state = readinessState();
    const errors = [];
    if (!field("title")?.value.trim()) errors.push("Добавьте заголовок");
    if (!state.content) errors.push("Заполните основной текст статьи");
    if (!state.category) errors.push("Выберите категорию");
    if (!state.excerpt) errors.push("Добавьте короткое описание");
    if (!hasCover()) errors.push("Добавьте обложку статьи");
    if (!field("seo_title")?.value.trim()) errors.push("Добавьте заголовок для поисковиков");
    if (!field("seo_description")?.value.trim()) errors.push("Добавьте описание для поисковиков");
    let selectedTags = [];
    try { selectedTags = JSON.parse(hidden.value || "[]"); } catch (_) { selectedTags = []; }
    if (!Array.isArray(selectedTags) || !selectedTags.some((tag) => String(tag).trim())) errors.push("Добавьте хотя бы один тег");
    if (!state.date) errors.push("Укажите дату публикации");
    document.querySelectorAll("[data-gallery-group]").forEach((group) => {
      const number = group.dataset.galleryNumber;
      const forms = [...group.querySelectorAll("[data-gallery-form]")].filter((item) => !item.classList.contains("hidden"));
      if (!forms.length) errors.push(`Добавьте хотя бы одно изображение в галерею №${number}`);
      forms.forEach((galleryForm, index) => {
        const file = galleryForm.querySelector("input[type='file']");
        const preview = galleryForm.querySelector("[data-gallery-image-preview]");
        const hasImage = Boolean(file?.files?.length || (preview?.getAttribute("src") && !preview.classList.contains("hidden")));
        const alt = galleryForm.querySelector("input[name$='-alt']");
        if (!hasImage) errors.push(`Выберите изображение ${index + 1} в галерее №${number}`);
        if (!alt?.value.trim()) errors.push(`Добавьте альтернативный текст к изображению ${index + 1} в галерее №${number}`);
      });
    });
    return errors;
  };

  articleForm.addEventListener("input", onChange);
  articleForm.addEventListener("change", onChange);
  document.addEventListener("cms-editor-change", onChange);
  document.addEventListener("cms-editor-ready", (event) => { mainEditor = event.detail.editor; initialize(); });
  coverInput?.addEventListener("change", () => {
    const selected = coverInput.files?.[0];
    const uploadError = selected ? imageFileError(selected) : "";
    if (uploadError) {
      coverInput.value = "";
      reportUploadError(uploadError);
      updateCoverPreview();
      return;
    }
    updateCoverPreview();
  });
  coverClear?.addEventListener("change", updateCoverPreview);
  coverPreview?.addEventListener("click", () => coverInput?.click());
  window.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") { event.preventDefault(); articleForm.requestSubmit(document.querySelector("#save-draft-button")); }
  });
  window.addEventListener("beforeunload", (event) => { if (dirty && !submitting) { event.preventDefault(); event.returnValue = ""; } });
  articleForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    window.tinymce?.triggerSave();
    const action = event.submitter?.value || "save";
    const status = field("status");
    if (status && action === "publish") status.value = "published";
    const errors = status?.value === "published" ? publicationErrors().filter((error) => error !== "Укажите дату публикации") : [];
    if (errors.length) {
      validationBox.classList.add("hidden");
      showErrorToast(errors, action === "publish" ? "Не удалось опубликовать" : "Не удалось сохранить черновик");
      return;
    }
    submitting = true;
    validationBox.classList.add("hidden");
    const buttons = [...articleForm.querySelectorAll("button[type='submit'][name='action']")];
    buttons.forEach((button) => { button.disabled = true; button.classList.add("opacity-50"); });
    try {
      const payload = new FormData(articleForm);
      payload.set("action", action);
      const submitUrl = articleForm.getAttribute("action") || window.location.href;
      const response = await fetch(submitUrl, {
        method: "POST",
        body: payload,
        headers: {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        submitting = false;
        showErrorToast(result.errors?.length ? result.errors : ["Не удалось сохранить статью"], action === "publish" ? "Не удалось опубликовать" : "Не удалось сохранить черновик");
        return;
      }
      dirty = false;
      safeStorage.remove();
      sessionStorage.setItem("zvezdach:cms-toast", JSON.stringify({message: result.message}));
      if (result.created && result.edit_url) window.location.assign(result.edit_url);
      else window.location.reload();
    } catch (_) {
      submitting = false;
      showErrorToast(["Сервер не ответил, попробуйте ещё раз"], action === "publish" ? "Не удалось опубликовать" : "Не удалось сохранить черновик");
    } finally {
      if (!submitting) buttons.forEach((button) => { button.disabled = false; button.classList.remove("opacity-50"); });
    }
  });
  const serverErrors = [...articleForm.querySelectorAll(".errorlist li")].map((item) => item.textContent.trim()).filter(Boolean);
  if (serverErrors.length) window.setTimeout(() => showErrorToast(serverErrors), 250);
  try {
    const flash = JSON.parse(sessionStorage.getItem("zvezdach:cms-toast") || "null");
    if (flash?.message) {
      sessionStorage.removeItem("zvezdach:cms-toast");
      window.requestAnimationFrame(() => {
        showSuccessToast(flash.message);
      });
    }
  } catch (_) { sessionStorage.removeItem("zvezdach:cms-toast"); }
  window.setTimeout(initialize, 800);
})();
