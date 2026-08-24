/** Plausible tagged custom events (see templates/_analytics.html). */

function plausiblePayload(extra) {
  const redacted = window.redactAnalyticsUrl(window.location.href);
  return { u: redacted, url: redacted, ...(extra || {}) };
}

function trackAnalyticsPageview() {
  if (typeof window.plausible !== "function" || typeof window.redactAnalyticsUrl !== "function") return;
  window.plausible("pageview", plausiblePayload());
}

function trackEvent(name, props) {
  if (typeof window.plausible !== "function" || typeof window.redactAnalyticsUrl !== "function") return;
  window.plausible(name, plausiblePayload(props ? { props } : undefined));
}

window.trackAnalyticsPageview = trackAnalyticsPageview;
