/* Idle Fantasy Viewer – i18n (English default / fallback) */

const I18n = (() => {
  const STORAGE_KEY = "locale";
  const SUPPORTED = ["en", "de"];
  let locale = "en";
  let preference = "auto";
  let messages = {};
  let fallback = {};

  function getNested(obj, path) {
    return path.split(".").reduce((o, k) => (o && o[k] !== undefined ? o[k] : undefined), obj);
  }

  async function loadMessages(code) {
    const res = await fetch(`/static/locales/${code}.json`);
    if (!res.ok) throw new Error(`Locale not found: ${code}`);
    return res.json();
  }

  function resolveLocale(pref) {
    if (pref === "en" || pref === "de") return pref;
    const browser = (navigator.language || "en").split("-")[0].toLowerCase();
    return SUPPORTED.includes(browser) ? browser : "en";
  }

  async function init() {
    preference = localStorage.getItem(STORAGE_KEY) || "auto";
    locale = resolveLocale(preference);
    fallback = await loadMessages("en");
    messages = locale === "en" ? fallback : await loadMessages(locale);
    document.documentElement.lang = locale;
    return locale;
  }

  async function setPreference(pref) {
    preference = pref;
    localStorage.setItem(STORAGE_KEY, pref);
    locale = resolveLocale(pref);
    messages = locale === "en" ? fallback : await loadMessages(locale);
    document.documentElement.lang = locale;
    return locale;
  }

  function t(key, params = {}) {
    let str = getNested(messages, key) ?? getNested(fallback, key) ?? key;
    if (typeof str !== "string") return key;
    return str.replace(/\{(\w+)\}/g, (_, k) => (params[k] !== undefined ? String(params[k]) : `{${k}}`));
  }

  function translateIssue(item) {
    const params = { ...(item.params || {}), field: item.field || "" };
    const translated = t(`import.${item.code}`, params);
    if (translated !== `import.${item.code}`) return translated;
    return item.message || translated;
  }

  function localeTag() {
    return locale === "de" ? "de-DE" : "en-US";
  }

  function getLocale() { return locale; }
  function getPreference() { return preference; }

  return { init, setPreference, t, translateIssue, localeTag, getLocale, getPreference, SUPPORTED };
})();

window.I18n = I18n;
window.t = (...args) => I18n.t(...args);
