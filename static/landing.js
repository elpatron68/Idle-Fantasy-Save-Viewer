document.addEventListener("DOMContentLoaded", async () => {
  await I18n.init();
  applyStaticI18n();
  setupLanguage();
  setupCreate();
});

function applyStaticI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
}

function setupLanguage() {
  const sel = document.getElementById("locale-select");
  sel.value = I18n.getPreference();
  sel.addEventListener("change", async (e) => {
    await I18n.setPreference(e.target.value);
    applyStaticI18n();
  });
}

function setupCreate() {
  const btn = document.getElementById("create-viewer");
  const status = document.getElementById("create-status");
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    status.hidden = false;
    status.textContent = t("viewer.creating");
    status.className = "landing-hint";
    try {
      const res = await fetch("/api/viewers", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || t("viewer.createFailed"));
      window.location.href = data.url;
    } catch (err) {
      status.textContent = err.message;
      status.className = "landing-hint landing-hint-error";
      btn.disabled = false;
    }
  });
}
