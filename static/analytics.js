/** Plausible tagged custom events (see templates/_analytics.html). */

function plausiblePayload(extra) {
  const redacted = window.redactAnalyticsUrl(window.location.href);
  const origin = window.location.origin;
  const u = redacted.startsWith("http") ? redacted : origin + redacted;
  return { u, url: u, ...(extra || {}) };
}

function trackAnalyticsPageview() {
  if (typeof window.plausible !== "function" || typeof window.redactAnalyticsUrl !== "function") return;
  window.plausible("pageview", plausiblePayload());
}

function trackEvent(name, props) {
  if (typeof window.plausible !== "function" || typeof window.redactAnalyticsUrl !== "function") return;
  window.plausible(name, plausiblePayload(props ? { props } : undefined));
}

function bootAnalytics() {
  trackAnalyticsPageview();
}

window.trackAnalyticsPageview = trackAnalyticsPageview;

document.addEventListener("DOMContentLoaded", bootAnalytics);
var plausibleScript = document.getElementById("plausible-script");
if (plausibleScript) {
  plausibleScript.addEventListener("load", bootAnalytics);
}
