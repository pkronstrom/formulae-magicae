// Isolated-world relay: the page world (overlay) cannot call chrome.runtime,
// and the service worker cannot be reached by page scripts. This 20-line shim
// forwards {prv:"http"} window messages to the worker and posts results back.
window.addEventListener("message", e => {
  if (e.source !== window || !e.data || e.data.prv !== "http") return;
  const { id, url, method, body, binary } = e.data;
  try {
    chrome.runtime.sendMessage({ url, method, body, binary }, resp => {
      window.postMessage(
        { prv: "http-result", id, resp: resp || { ok: false, why: "no response" } }, "*");
    });
  } catch (err) {
    window.postMessage(
      { prv: "http-result", id, resp: { ok: false, why: String(err).slice(0, 120) } }, "*");
  }
});
// Announce the bridge so the overlay knows local audio is possible.
window.postMessage({ prv: "bridge-ready" }, "*");
