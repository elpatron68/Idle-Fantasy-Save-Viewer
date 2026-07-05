/** Plausible tagged custom events (see templates/_analytics.html). */
function trackEvent(name, props) {
  if (typeof window.plausible === "function") {
    window.plausible(name, props ? { props } : undefined);
  }
}
