/* PWA – service worker registration and install hint */

const Pwa = (() => {
  const DISMISS_KEY = "pwa-hint-dismissed";
  let deferredPrompt = null;
  let refreshInstallHint = null;

  function isStandalone() {
    return window.matchMedia("(display-mode: standalone)").matches
      || window.navigator.standalone === true;
  }

  function detectPlatform() {
    const ua = navigator.userAgent;
    if (/iPad|iPhone|iPod/.test(ua)) return "ios";
    if (/Android/.test(ua)) return "android";
    return "desktop";
  }

  function swConfig() {
    const viewerId = document.body?.dataset?.viewerId;
    if (viewerId && viewerId !== "local") {
      return { url: `/v/${viewerId}/sw.js`, scope: `/v/${viewerId}/` };
    }
    return { url: "/sw.js", scope: "/" };
  }

  async function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    const { url, scope } = swConfig();
    try {
      await navigator.serviceWorker.register(url, { scope });
    } catch {
      /* SW is optional – manual install instructions still apply */
    }
  }

  function platformHintKey() {
    const platform = detectPlatform();
    if (platform === "ios") return "pwa.hintIos";
    if (platform === "android") return "pwa.hintAndroid";
    return "pwa.hintDesktop";
  }

  function setupInstallHint() {
    if (isStandalone()) return null;
    if (localStorage.getItem(DISMISS_KEY) === "1") return null;

    const hint = document.getElementById("pwa-install-hint");
    if (!hint) return null;

    const body = document.getElementById("pwa-hint-body");
    const installBtn = document.getElementById("pwa-install-btn");
    const dismissBtn = document.getElementById("pwa-hint-dismiss");

    const updateHintText = () => {
      const title = hint.querySelector("[data-i18n='pwa.hintTitle']");
      if (title) title.textContent = t("pwa.hintTitle");
      if (body && !deferredPrompt) body.textContent = t(platformHintKey());
      if (body && deferredPrompt) body.textContent = t("pwa.hintBody");
      if (dismissBtn) dismissBtn.title = t("actions.dismiss");
      if (installBtn && !installBtn.hidden) installBtn.textContent = t("pwa.install");
    };

    hint.hidden = false;
    updateHintText();

    window.addEventListener("beforeinstallprompt", (e) => {
      e.preventDefault();
      deferredPrompt = e;
      if (installBtn) installBtn.hidden = false;
      if (body) body.textContent = t("pwa.hintBody");
      updateHintText();
    });

    dismissBtn?.addEventListener("click", () => {
      localStorage.setItem(DISMISS_KEY, "1");
      hint.hidden = true;
    });

    installBtn?.addEventListener("click", async () => {
      if (!deferredPrompt) return;
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      deferredPrompt = null;
      installBtn.hidden = true;
      if (outcome === "accepted") {
        if (body) body.textContent = t("pwa.installed");
        setTimeout(() => { hint.hidden = true; }, 3000);
      } else {
        updateHintText();
      }
    });

    return updateHintText;
  }

  async function init() {
    await registerServiceWorker();
    refreshInstallHint = setupInstallHint();
  }

  function refreshHint() {
    refreshInstallHint?.();
  }

  return { init, refreshHint };
})();

window.Pwa = Pwa;
