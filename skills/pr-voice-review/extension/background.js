// Service worker: the only context allowed to reach http://127.0.0.1 from a
// github.com page (host_permissions bypasses the page CSP that blocks it).
// Fetches on behalf of the overlay and returns audio as base64.
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || !msg.url || !/^http:\/\/127\.0\.0\.1:\d+\//.test(msg.url)) {
    sendResponse({ ok: false, why: "refused: only 127.0.0.1 urls" });
    return false;
  }
  const opts = { method: msg.method || "GET" };
  if (msg.body) {
    opts.body = msg.body;
    opts.headers = { "Content-Type": "application/json" };
  }
  fetch(msg.url, opts)
    .then(async r => {
      if (msg.binary) {
        const buf = new Uint8Array(await r.arrayBuffer());
        let s = "";
        for (let i = 0; i < buf.length; i += 32768)
          s += String.fromCharCode.apply(null, buf.subarray(i, i + 32768));
        sendResponse({ ok: r.ok, b64: btoa(s), type: r.headers.get("content-type") || "audio/wav" });
      } else {
        sendResponse({ ok: r.ok, text: await r.text() });
      }
    })
    .catch(e => sendResponse({ ok: false, why: String(e).slice(0, 200) }));
  return true; // async sendResponse
});
