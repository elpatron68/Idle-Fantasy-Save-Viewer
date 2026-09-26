/** Plausible tagged custom events — all logic in this file (CSP allows no inline scripts). */

window.plausible = window.plausible || function () {
  (window.plausible.q = window.plausible.q || []).push(arguments);
};
window.plausible.l = +new Date;

function redactViewerUrl(url) {
  try {
    const parsed = new URL(url, window.location.origin);
    parsed.pathname = parsed.pathname.replace(/^\/v\/[^/]+\/?/, "/v/viewer/");
    if (parsed.pathname === "/v/viewer") parsed.pathname = "/v/viewer/";
    parsed.search = "";
    return parsed.pathname + parsed.hash;
  } catch (e) {
    return String(url).replace(/\/v\/[^/]+\/?/, "/v/viewer/").split("?")[0];
  }
}

window.redactAnalyticsUrl = redactViewerUrl;

function isViewerPathname(pathname) {
  return /^\/v\/[^/]+\/?/.test(pathname || "");
}

function viewerAnalyticsUrl() {
  const hash = window.location.hash || "#overview";
  return `${window.location.origin}/v/viewer/${hash}`;
}

function plausiblePayload(extra) {
  let u;
  if (isViewerPathname(window.location.pathname)) {
    u = viewerAnalyticsUrl();
  } else {
    const redacted = redactViewerUrl(window.location.href);
    u = redacted.startsWith("http") ? redacted : window.location.origin + redacted;
  }
  return { u, ...(extra || {}) };
}

function trackAnalyticsPageview() {
  if (typeof window.plausible !== "function") return;
  window.plausible("pageview", plausiblePayload());
}

function trackEvent(name, props) {
  if (typeof window.plausible !== "function") return;
  window.plausible(name, plausiblePayload(props ? { props } : undefined));
}

function trackViewerOpen() {
  if (!isViewerPathname(window.location.pathname)) return;
  trackEvent("Viewer Open");
  trackAnalyticsPageview();
}

function trackViewerTab(tab) {
  if (!isViewerPathname(window.location.pathname)) return;
  trackEvent("Viewer Tab", { tab: tab || "overview" });
  trackAnalyticsPageview();
}

function bootAnalytics() {
  if (typeof window.plausible !== "function") return;
  if (isViewerPathname(window.location.pathname)) {
    trackViewerOpen();
    return;
  }
  trackAnalyticsPageview();
}

let analyticsBootSent = false;
function bootAnalyticsOnce() {
  if (analyticsBootSent) return;
  if (typeof window.plausible !== "function") return;
  analyticsBootSent = true;
  bootAnalytics();
}

window.trackAnalyticsPageview = trackAnalyticsPageview;
window.trackViewerTab = trackViewerTab;

document.addEventListener("DOMContentLoaded", bootAnalyticsOnce);
window.addEventListener("load", bootAnalyticsOnce);

window.addEventListener("hashchange", () => {
  if (isViewerPathname(window.location.pathname)) return;
  const tab = (window.location.hash || "#overview").replace(/^#/, "") || "overview";
  trackViewerTab(tab);
});

const plausibleScript = document.getElementById("plausible-script");
if (plausibleScript) {
  plausibleScript.addEventListener("load", bootAnalyticsOnce);
}
