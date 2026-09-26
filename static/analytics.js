/** Plausible tagged custom events (see templates/_analytics.html). */

function isViewerPathname(pathname) {
  return /^\/v\/[^/]+\/?/.test(pathname || "");
}

function viewerAnalyticsUrl() {
  const hash = window.location.hash || "#overview";
  return `${window.location.origin}/v/viewer/${hash}`;
}

function plausiblePayload(extra) {
  const redacted = typeof window.redactAnalyticsUrl === "function"
    ? window.redactAnalyticsUrl(window.location.href)
    : window.location.href;
  let u = redacted.startsWith("http") ? redacted : window.location.origin + redacted;
  if (isViewerPathname(window.location.pathname)) {
    u = viewerAnalyticsUrl();
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

let analyticsBootDone = false;
function bootAnalyticsOnce() {
  if (analyticsBootDone) return;
  analyticsBootDone = true;
  bootAnalytics();
}

window.trackAnalyticsPageview = trackAnalyticsPageview;
window.trackViewerTab = trackViewerTab;

document.addEventListener("DOMContentLoaded", bootAnalyticsOnce);
window.addEventListener("load", bootAnalyticsOnce);

window.addEventListener("hashchange", () => {
  if (!isViewerPathname(window.location.pathname)) return;
  const tab = (window.location.hash || "#overview").replace(/^#/, "") || "overview";
  trackViewerTab(tab);
});

var plausibleScript = document.getElementById("plausible-script");
if (plausibleScript) {
  plausibleScript.addEventListener("load", bootAnalyticsOnce);
}
