// pr-voice-review overlay — the walkthrough control bar on GitHub's Files-changed page.
//
// THIS FILE IS THE EVENT CONTRACT. SKILL.md references it; do not restate it there.
//
// window.__prv API (v2):
//   mount()                        build (or rebuild) the bar
//   load(segments[, startAt])      REPLACE all segments (keeps you on the same path)
//   fill(i, {role, notes, speech, text, from, to})
//                                  MERGE into one segment — the progressive path;
//                                  never moves the user, keeps their own notes
//   go(i[, c][, play])             jump to segment i (scroll + highlight + render)
//   goBeat(i, c[, play])           move the observation cursor (see below)
//   showNote(si, ni)               highlight note ni of segment si
//   addUserNote(i, text)           append a user note card to segment i
//   collectNotes()                 -> [{path, from, to, text, byUser, flag}] —
//                                  the user's own cards PLUS any of yours they
//                                  flagged. flagged() is just that subset.
//   wait(ms)                       resolve next queued event, or {action:"TIMEOUT"}
//   drain()                        -> all queued events, clearing the queue
//   i / c / segments / auto / silent   current state, readable at any time
//   unmount()                      remove everything
//
// Segment shape — multiple notes per file, each with its own optional range:
//   { path, sha, tier, stat, role, speech,
//     notes: [{from, to, text, speech, svg, byUser}] }
//   tier: crucial | normal | skim | ignore.  text is md-lite: `code`, **bold**.
//   role: one sentence on what the file is and its part in the whole PR —
//   rendered as a dimmed line under the header, above the note cards.
//   sha: omit for a non-file segment (the phase-0 PR overview) — no scrolling,
//   no highlight, no notrendered. Segment 0 SHOULD be such an overview, and it
//   leads with the problem this PR solves and how, in plain language and with no
//   identifiers, before any reviewer triage. See SKILL.md — it is the one part
//   written for someone who does not know the codebase.
//   svg: optional agent-authored inline SVG (a small flow/architecture sketch)
//   rendered inside the card under the text. Agent content only — never user input.
//
// OBSERVATION CURSOR. Narration is split into chunks and the walk pauses between
// them, so a chunk is one thing said about one place in the code:
//   seg.speech      the file's opening line — chunk 0, no line range
//   note.speech     one chunk each, anchored to that note's from/to
// A note WITHOUT `speech` is a silent card (user comments, Q&A). A segment where
// no note carries speech collapses to a single chunk of seg.speech — the old
// one-gate-per-file behaviour, so reviews authored before this still play.
//
// PRV.c indexes the current chunk. Prev/Next walk chunks and roll across file
// boundaries; « and » (shift+B / shift+N) skip whole files.
//
// TWO SWITCHES, one meaning each:
//   auto (a)    who advances the cursor — the timer, or you. Off still speaks
//               every observation; you just choose when the next one starts.
//               Turning it off lets the current chunk finish, then parks.
//   silent (k)  whether anything is spoken. Off is the read-it-yourself mode:
//               Next and clicking a block still move, light the diff lines and
//               swap the transcript — they just say nothing.
// They were one flag called `muted` that actually meant autoplay, so there was
// no way to be quiet: deliberate navigation forces playback past an autoplay-off.
// Silence SUSPENDS auto rather than clearing it (autoOn() is the effective
// value), because without audio there is no duration to pace a walk by.
//
// SPEED (x) cycles 1/1.25/1.5/1.75/2. The server time-stretches with ffmpeg's
// atempo, so the voice keeps its pitch — resampling to 2x would raise it an
// octave. Audio is never re-synthesised; /play reports wall-clock duration
// already divided by the rate, so the word walk and the chain stay correct.
//
// Play NEVER advances — it speaks the block you are on. Next moves you. One
// verb each; ▶ used to jump forward once a block had finished, duplicating a
// control two slots away.
//
// Clicking a block moves the cursor to that observation and speaks it. Each
// block also carries a ⚑ on hover. A flag means "this point wants more" and
// nothing stronger — it is durable, and collectNotes() carries it to wrap-up
// whatever the agent does. Nothing stops the agent digging in the moment it
// arrives, and it usually will; that is opportunistic, not promised, which is
// why no separate "ask" control is needed.
//
// PAUSE resumes where it stopped: the page remembers the file offset and /play
// takes an `at` to restart from it. SIGSTOP does suspend the player, but afplay
// never finishes afterwards (measured: a 3s remainder still running 15s later),
// so seeking is the reliable route.
//
// TRANSCRIPT (T, or the t key). Shows the current chunk's text and lights each
// word as it is spoken. Kokoro emits no timestamps, so timing is derived from the
// chunk's measured duration, weighting each word by length and buying extra time
// at punctuation; the walk runs off wall-clock from the moment /play returned,
// since server-side playback gives no timeupdate. Error stays inside one chunk.
//
// Events the agent receives from wait()/drain():
//   position    {i, c, played, why}
//                        — user navigated locally; COALESCED: many fast clicks
//                          collapse to one event with the final index. NEVER speak
//                          on this. `why` distinguishes the user choosing silence
//                          ("muted", "autoplay-off") from an actual fault
//                          ("not-rendered", "play-failed", "no-bridge"); the bare
//                          played:false it replaced conflated the two, and agents
//                          read a deliberate silence as something to talk over.
//   say         {text, i, c, ni, path, from, to}
//                        — typed question; answer it (voice + terminal). It
//                          carries WHERE they were, so "what does this do?" is
//                          answerable: from/to is the block under the cursor.
//   comment     {i, c, ni, path, from, to, text}
//                        — user added a note card, already stored in the page,
//                          anchored to the block they were on. from/to is what
//                          an inline review comment gets filed against; it is
//                          null only on the overview or a file's intro line.
//   flag        {i, ni, on, path, from, to, text}
//                        — on:true marks THAT observation as wanting more.
//                          Dig in and fill a deeper note when you have room;
//                          it is stored in the page, so it keeps until you do.
//                          on:false means they cleared it.
//   repeat/stop          — say again / tts.sh --stop
//   notrendered {i}      — GitHub lazy-loaded that file; navigate via sidebar
//   end                  — the walk is over. The page has ALREADY swapped itself
//                          for a completion card and is showing a status line,
//                          so wrap up at once and keep setStatus() current. Do
//                          not wait to be asked for a summary.
//   TIMEOUT              — nothing happened within the wait window
//
// Navigation, note cards, add/remove, and highlighting are all local and instant.
// The agent is only woken by the events above. mute/auto are flags, not requests.

(() => {
  const PRV = (window.__prv = window.__prv || {
    queue: [], waiter: null, segments: [], i: 0, c: 0
  });
  // Two switches, deliberately separate. `auto` is who advances the cursor —
  // the timer or you. `silent` is whether anything is spoken at all. They were
  // one flag named `muted` that actually meant autoplay, which left no way to
  // read the review in silence: navigating forces playback past an autoplay-off.
  PRV.auto = !!PRV.auto;              // default off — no surprise audio on load
  PRV.silent = !!PRV.silent;
  const autoOn = () => PRV.auto && !PRV.silent;
  PRV.v = 55;
  if (PRV.c == null) PRV.c = 0;
  // The LENS the walk is narrated through. Chosen once and fixed for the session.
  // Not a volume dial — architect is not guided with the detail deleted, it is the
  // same file described from higher up: what it is for, where it sits, what this
  // change means for the system. Line-level points are what it drops, not substance.
  //   guided     every observation, gated at each — the close read
  //   focused    close read on crucial files, the higher lens everywhere else
  //   architect  every file from the higher lens; you read the lines yourself
  PRV.depth = PRV.depth || "guided";

  // The unit the walk pauses between: one thing said about one place in the code.
  // The server derives the identical list from the same fields (chunks_of in
  // server.py), so neither side has to publish a manifest for the other — keep
  // the two rules in step.
  const chunksOf = seg => {
    if (!seg) return [];
    const intro = (seg.speech || "").trim();
    const notes = seg.notes || [];
    const lead = intro ? [{ text: intro, from: null, to: null, ni: -1 }] : [];
    const all = !notes.some(n => n && (n.speech || "").trim()) ? lead
      : lead.concat(notes.reduce((out, n, ni) => {
          if (n && (n.speech || "").trim())
            out.push({ text: n.speech.trim(), from: n.from, to: n.to, ni });
          return out;
        }, []));
    // Depth decides how far down the walk goes. Enforced here rather than only
    // in what the agent writes, so a review authored in guided can be re-walked
    // at overview from cache without touching a word of it.
    if (PRV.depth === "guided" || all.length < 2) return all;
    if (PRV.depth === "focused" && seg.tier === "crucial") return all;
    return all.slice(0, 1);          // the file's own account of itself
  };
  PRV.chunksOf = chunksOf;
  PRV.setDepth = d => {
    if (["guided", "focused", "architect"].indexOf(d) < 0) return PRV.depth;
    PRV.depth = d;
    PRV.c = 0;
    if (document.getElementById("prv-overlay")) render();
    return d;
  };
  // An unauthored file still has to be visitable, so it counts as one empty beat.
  PRV.beatCount = i => Math.max(1, chunksOf(PRV.segments[i]).length);
  PRV.nextBeat = () => {
    if (PRV.c + 1 < PRV.beatCount(PRV.i)) return { i: PRV.i, c: PRV.c + 1 };
    if (PRV.i + 1 < PRV.segments.length) return { i: PRV.i + 1, c: 0 };
    return null;
  };
  PRV.prevBeat = () => {
    if (PRV.c > 0) return { i: PRV.i, c: PRV.c - 1 };
    if (PRV.i > 0) return { i: PRV.i - 1, c: PRV.beatCount(PRV.i - 1) - 1 };
    return null;
  };

  // Where the user currently IS — the block under the cursor. Anything they type
  // is about this, so both comments and questions carry it: a review comment
  // without a line range cannot be filed inline, and "what does this do?" is
  // unanswerable without knowing what "this" was.
  const here = () => {
    const s = PRV.segments[PRV.i] || {};
    const k = chunksOf(s)[PRV.c] || {};
    return { path: s.path || null, from: k.from || null,
             to: k.to || k.from || null, ni: k.ni != null ? k.ni : -1 };
  };
  PRV.here = here;
  const rangeLabel = a =>
    a.from ? `L${a.from}${a.to && a.to !== a.from ? "–" + a.to : ""}` : "";

  // ---- local bridge (extension service worker -> 127.0.0.1 server) --------
  // When the bridge links, events go to the server (the agent curls /wait — no
  // browser round trip) and audio plays in-page (stop/mute/repeat = instant).
  // Without it, everything falls back to the in-page queue + agent audio.
  PRV.server = PRV.server || "http://127.0.0.1:8765";
  PRV.linked = false;
  PRV._rpc = PRV._rpc || {};
  PRV.bridge = (url, opts = {}) => new Promise(res => {
    const id = Math.random().toString(36).slice(2);
    PRV._rpc[id] = res;
    setTimeout(() => { if (PRV._rpc[id]) { delete PRV._rpc[id]; res({ ok: false, why: "bridge timeout" }); } }, 8000);
    window.postMessage({ prv: "http", id, url, ...opts }, "*");
  });
  if (!PRV._bridgeHook) {
    PRV._bridgeHook = e => {
      if (e.source !== window || !e.data) return;
      if (e.data.prv === "http-result") {
        const cb = PRV._rpc[e.data.id];
        if (cb) { delete PRV._rpc[e.data.id]; cb(e.data.resp); }
      } else if (e.data.prv === "bridge-ready") {
        // Keep trying: the server may start after the page loaded, and segments
        // may arrive minutes into the session. Mount a visible "preparing" bar
        // the moment the server answers, then poll until content lands.
        const tryLink = () => {
          if (PRV.segments.length) return;
          PRV.bridge(PRV.server + "/ping").then(r => {
            PRV.linked = !!(r && r.ok);
            if (!PRV.linked) return setTimeout(tryLink, 4000);
            if (!document.getElementById("prv-overlay")) {
              PRV.mount();
              const role = document.getElementById("prv-role");
              if (role) { role.textContent = "Preparing the review — files appear as the agent works\u2026"; role.style.display = ""; }
            }
            PRV.bridge(PRV.server + "/segments").then(sr => {
              if (sr.ok && sr.text) {
                try { const segs = JSON.parse(sr.text); if (Array.isArray(segs) && segs.length) {
                  PRV.segments = segs;
                  PRV.restore();          // flags, geometry and toggles, before first paint
                  PRV.load(segs, (PRV._restored || {}).i || 0);
                  if (PRV._restored) { PRV.c = PRV._restored.c || 0; render(); }
                  PRV.bridge(PRV.server + "/status").then(st => {
                    if (st.ok && st.text) {
                      try {
                        const j0 = JSON.parse(st.text);
                        PRV.ready = new Set(j0.renderedChunks || (j0.renderedIdx || []).map(k => k + ":0"));
                        PRV.renderedFiles = j0.rendered || 0;
                      } catch (_) {}
                    }
                    render();
                  });
                  PRV.autoRefresh();
                  return;
                } }
                catch (_) {}
              }
              setTimeout(tryLink, 3000);
            });
          });
        };
        tryLink();
      }
    };
    window.addEventListener("message", PRV._bridgeHook);
  }

  const push = ev => {
    ev.at = Date.now();
    if (PRV.linked) {                      // server path: agent is curling /wait
      PRV.bridge(PRV.server + "/event", { method: "POST", body: JSON.stringify(ev) })
        .then(r => { if (!r.ok) { PRV.linked = false; pushLocal(ev); } });
      return;
    }
    pushLocal(ev);
  };
  const pushLocal = ev => {
    if (PRV.waiter) { const w = PRV.waiter; PRV.waiter = null; w(ev); }
    else PRV.queue.push(ev);
  };
  // position events coalesce: replace any unconsumed one instead of stacking.
  const pushPosition = () => {
    const ev = { action: "position", i: PRV.i, c: PRV.c };
    if (PRV.waiter) return push(ev);
    const k = PRV.queue.findIndex(e => e.action === "position");
    if (k >= 0) { ev.at = Date.now(); PRV.queue[k] = ev; } else push(ev);
  };

  const dark = () => matchMedia("(prefers-color-scheme: dark)").matches;
  const esc = s => String(s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  // md-lite: `code` and **bold** only — enough for review prose, no library.
  const md = s => esc(s)
    .replace(/`([^`]+)`/g, '<code style="font-family:ui-monospace,monospace;font-size:12px;padding:1px 5px;border-radius:4px;background:rgba(110,118,129,.22)">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  const TIERS = { crucial: "\u{1F534}", normal: "\u{1F7E1}", skim: "\u{26AA}", ignore: "\u{2B1C}" };

  // ---- highlight ----------------------------------------------------------
  const ensureStyle = () => {
    if (document.getElementById("prv-style")) return;
    const s = document.createElement("style");
    s.id = "prv-style";
    s.textContent = `
      @keyframes prv-pulse {
        0%   { box-shadow: inset 3px 0 0 0 #f78166, inset 0 0 0 999px rgba(247,129,102,.20); }
        100% { box-shadow: inset 3px 0 0 0 #f78166, inset 0 0 0 999px rgba(247,129,102,.11); }
      }
      tr.prv-hl > td, tr.prv-hl > th { animation: prv-pulse 1s ease-out 1; animation-fill-mode: forwards; }

      /* One button rule, so every control is the same height and the states are
         consistent. Inline styles per button drifted and could not express
         :hover or :focus-visible at all. */
      #prv-overlay button {
        cursor: pointer; font: inherit; font-size: 12px; line-height: 1;
        height: 26px; padding: 0 10px; border-radius: 6px;
        border: 1px solid var(--prv-bd); background: transparent; color: var(--prv-fg);
        display: inline-flex; align-items: center; justify-content: center;
        transition: background .12s, border-color .12s;
      }
      #prv-overlay button:hover { background: rgba(110,118,129,.18); }
      /* A click left the ring stuck on; keyboard focus still needs to show. */
      #prv-overlay button:focus { outline: none; }
      #prv-overlay button:focus-visible { outline: 2px solid #58a6ff; outline-offset: 1px; }
      #prv-overlay button[data-on="1"] {
        background: #1f6feb; border-color: #388bfd; color: #fff;
      }
      #prv-overlay button[data-on="1"]:hover { background: #388bfd; }
      #prv-overlay button[data-primary="1"] {
        background: #238636; border-color: #2ea043; color: #fff;
      }
      #prv-overlay button[data-primary="1"]:hover { background: #2ea043; }

      /* The narration reads as speech, not as another finding: its own warm
         ground, italic, and the accent bar that ties it to the lit diff lines. */
      #prv-script {
        border-left: 3px solid #f78166;
        background: rgba(247,129,102,.09);
        font-style: italic;
      }
      #prv-script span[data-w] { border-radius: 3px; transition: background .12s; }

      /* Square where the accent is. A radius on that edge bends the 3px border
         into a curved sliver, which is what made these read as lumpy pills
         rather than callouts. */
      #prv-script, .prv-note { border-radius: 0 6px 6px 0; }

      /* One per-block action, hidden until hover so a clean panel stays clean.
         The flag is both "dig into this now" and "remember it" — the agent acts
         on the event immediately, and the mark survives to wrap-up if it cannot.
         A separate ? button would have been a second control for the same thing. */
      .prv-act {
        align-self: flex-start; opacity: 0; cursor: pointer; user-select: none;
        padding: 4px 8px; margin: -3px -3px -3px 0; border-radius: 4px;
        font-size: 12px; line-height: 1.2;
        transition: opacity .12s, background .12s;
      }
      .prv-note:hover .prv-act { opacity: .5; }
      .prv-act:hover { opacity: 1 !important; background: rgba(210,153,34,.28); }
      .prv-note[data-flag] .prv-flag { opacity: 1; color: #d29922; }
      .prv-note[data-flag] { box-shadow: inset 3px 0 0 0 #d29922; }

      .prv-note { transition: box-shadow .15s, background .15s; }
      .prv-note:hover { filter: brightness(1.12); }
      .prv-note.prv-now {
        box-shadow: inset 0 0 0 1px rgba(247,129,102,.6);
        background: rgba(247,129,102,.10) !important;
      }
      /* data-tip belongs to the header row ONLY. Inside #prv-notes the ::after
         is a nowrap absolutely-positioned child, which still counts toward that
         container's scrollable area: hovering grew it sideways, the horizontal
         scrollbar appeared, the reflow changed the vertical one, and the two
         fought each other into a flicker. Use a native title= in there. */
      #prv-overlay [data-tip] { position: relative; }
      #prv-overlay [data-tip]:hover::after {
        content: attr(data-tip); position: absolute; bottom: calc(100% + 7px);
        left: 50%; transform: translateX(-50%); white-space: nowrap;
        background: #1c2128; color: #e6edf3; border: 1px solid #30363d;
        padding: 3px 9px; border-radius: 5px; font-size: 11px; z-index: 1;
        pointer-events: none;
      }`;
    document.head.appendChild(s);
  };

  PRV.clearHighlight = () =>
    (document.querySelectorAll("tr.prv-hl").forEach(t => t.classList.remove("prv-hl")), true);

  PRV.highlight = (sha, from, to, side = "right") => {
    ensureStyle(); PRV.clearHighlight();
    const file = document.getElementById("diff-" + sha);
    if (!file) return { ok: false, why: "file not in DOM" };
    // Feature-detect GitHub's current diff markup rather than failing silently.
    if (!document.querySelector("tr.diff-line-row"))
      return { ok: false, why: "diff markup changed — selectors need updating" };
    const rows = [...file.querySelectorAll("tr.diff-line-row")].filter(tr => {
      const c = tr.querySelector(`[data-diff-side="${side}"][data-line-number]`);
      const n = c && +c.getAttribute("data-line-number");
      return n && n >= from && n <= to;
    });
    rows.forEach(tr => tr.classList.add("prv-hl"));
    if (rows[0]) {
      const r = rows[0].getBoundingClientRect();
      if (r.top < 80 || r.bottom > innerHeight - 230)
        window.scrollBy({ top: r.top - innerHeight * 0.3, behavior: "smooth" });
    }
    return { ok: true, matched: rows.length };
  };

  // ---- bar ---------------------------------------------------------------
  PRV.mount = () => {
    document.getElementById("prv-overlay")?.remove();
    ensureStyle();
    const d = dark();
    const fg = d ? "#e6edf3" : "#1f2328";
    const bd = d ? "#30363d" : "#d1d9e0";
    const btn = (label, a, title, primary) =>
      `<button data-a="${a}" data-tip="${title}"${primary ? ' data-primary="1"' : ""}>${label}</button>`;

    const o = document.createElement("div");
    o.id = "prv-overlay";
    o.innerHTML = `
      <div id="prv-head-drag" title="drag to move &middot; double-click to re-dock"></div>
      <div data-v="up" title="drag to resize" style="position:absolute;top:-4px;left:0;right:0;height:10px;cursor:ns-resize"></div>
      <div data-v="down" title="drag to resize" style="position:absolute;bottom:-4px;left:0;right:0;height:10px;cursor:ns-resize"></div>
      <div data-h="l" title="drag to widen" style="position:absolute;left:-4px;top:0;bottom:0;width:10px;cursor:ew-resize"></div>
      <div data-h="r" title="drag to widen" style="position:absolute;right:-4px;top:0;bottom:0;width:10px;cursor:ew-resize"></div>
      <div data-v="up" data-h="l" title="drag to resize both ways" style="position:absolute;top:-5px;left:-5px;width:18px;height:18px;cursor:nwse-resize;z-index:2"></div>
      <div data-v="up" data-h="r" title="drag to resize both ways" style="position:absolute;top:-5px;right:-5px;width:18px;height:18px;cursor:nesw-resize;z-index:2"></div>
      <div data-v="down" data-h="l" title="drag to resize both ways" style="position:absolute;bottom:-5px;left:-5px;width:18px;height:18px;cursor:nesw-resize;z-index:2"></div>
      <div data-v="down" data-h="r" title="drag to resize both ways" style="position:absolute;bottom:-5px;right:-5px;width:18px;height:18px;cursor:nwse-resize;z-index:2"></div>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <span data-a="fold" id="prv-fold" data-tip="collapse (h)"
          style="cursor:pointer;opacity:.6;font-size:11px;user-select:none;padding:0 2px">&#9662;</span>
        <span id="prv-count" style="font-weight:600;font-variant-numeric:tabular-nums"></span>
        <span id="prv-tier"></span>
        <code id="prv-path" style="font-size:12px;opacity:.85"></code>
        <span id="prv-stat" style="font-size:12px;opacity:.6"></span>
        <span style="margin-left:auto;display:flex;gap:5px;align-items:center">
          ${btn("&#9654;", "play", "play / pause narration (p)")}
          <span id="prv-beat" data-tip="observation within this file"
            style="font-size:11px;opacity:.6;font-variant-numeric:tabular-nums;min-width:26px;text-align:center"></span>
          <span id="prv-flags" data-tip="your flagged points — click to visit the next one"
            style="display:none;cursor:pointer;font-size:11px;color:#d29922;padding:1px 6px;
                   border-radius:4px;background:rgba(210,153,34,.16);white-space:nowrap"></span>
          ${btn("1&times;", "rate", "narration speed (x)")}
          <button data-a="auto" id="prv-auto" data-tip="autoplay: hands-free walk (a)">Auto</button>
          <button data-a="silent" id="prv-silent" data-tip="mute the narration and just read (k)">Mute</button>
          ${btn("T", "script", "show the narration text and follow it word by word (t)")}
          <span style="width:1px;height:18px;background:${bd};margin:0 3px"></span>
          ${btn("Comment", "comment", "add a note on this file (c)")}
          <span style="width:1px;height:18px;background:${bd};margin:0 3px"></span>
          ${btn("&laquo;", "rwd", "skip back to the previous file (shift+B)")}
          ${btn("&lsaquo; Prev", "back", "previous observation (b)")}
          ${btn("Next &rsaquo;", "next", "next observation (n)", true)}
          ${btn("&raquo;", "ffwd", "skip to the next file (shift+N)")}
        </span>
      </div>
      <div id="prv-role" style="margin-top:7px;font-size:12.5px;line-height:1.45;opacity:.72;font-style:italic"></div>
      <div id="prv-done" style="display:none;margin-top:10px;padding:14px 16px;border-radius:8px;
        background:rgba(63,185,80,.10);border:1px solid rgba(63,185,80,.45)"></div>
      <div id="prv-script" style="display:none;margin-top:9px;max-height:120px;overflow-y:auto;
        font-size:13px;line-height:1.7;padding:10px 13px"></div>
      <div id="prv-notes" style="margin-top:9px;max-height:180px;overflow-y:auto;overflow-x:hidden;display:flex;flex-direction:column;gap:8px;padding-right:2px"></div>
      <div id="prv-chip" style="display:none;margin-top:8px;font-size:11.5px;cursor:pointer;
        color:#f78166;background:rgba(247,129,102,.13);border:1px solid rgba(247,129,102,.4);
        border-radius:5px;padding:3px 9px;width:fit-content"></div>
      <input id="prv-input" placeholder="Ask a question — Enter to send"
        style="margin-top:8px;width:100%;box-sizing:border-box;border-radius:6px;padding:6px 9px;font:inherit;font-size:12.5px;background:${d ? "#0d1117" : "#f6f8fa"};color:${fg};border:1px solid ${bd}">
      <div id="prv-progress" style="height:3px;background:${bd};border-radius:2px;margin-top:8px">
        <div id="prv-bar" style="width:0%;height:100%;background:#238636;border-radius:2px;transition:width .25s"></div>
      </div>`;
    o.style.setProperty("--prv-fg", fg);        // the CSS button rules read these
    o.style.setProperty("--prv-bd", bd);
    Object.assign(o.style, {
      position: "fixed", left: "16px", right: "16px", bottom: "16px", overflow: "visible",
      zIndex: "2147483647", maxWidth: "1100px", margin: "0 auto",
      background: d ? "rgba(22,27,34,.97)" : "rgba(255,255,255,.98)",
      color: fg, border: `1px solid ${bd}`, borderRadius: "10px",
      padding: "12px 14px", boxShadow: "0 8px 28px rgba(0,0,0,.35)",
      font: "13px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
      backdropFilter: "blur(6px)"
    });
    document.body.appendChild(o);
    o.querySelector("#prv-fold").addEventListener("click", () => PRV.setFold(!PRV.folded));
    o.querySelector("#prv-flags").addEventListener("click", () => PRV.gotoFlag());
    o.querySelector("#prv-chip").addEventListener("click", () => PRV.setCommentMode(false));

    // Move the whole panel: drag the header row's empty background. Buttons and
    // inputs keep their own behavior; double-click re-docks to the bottom.
    const head = o.querySelector("div[style*='flex-wrap']");
    head.style.cursor = "move";
    // Anything you can click lives in this row, and dragging or re-docking must
    // not fire from it. `[data-a]` covers the caret and every button — the caret
    // is a span, so it used to fall through: collapse then expand read as a
    // double-click on the header and re-docked the panel you had just moved.
    // One constant for both handlers, because they had already drifted apart.
    const INERT = "button, input, code, [data-a], #prv-flags, #prv-beat, #prv-depth";
    head.addEventListener("mousedown", e => {
      if (e.target.closest(INERT)) return;
      e.preventDefault();
      const r = o.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
      const move = ev => {
        PRV.userPos = {
          left: Math.max(0, Math.min(ev.clientX - dx, innerWidth - r.width)),
          top: Math.max(0, Math.min(ev.clientY - dy, innerHeight - 60))
        };
        Object.assign(o.style, { left: PRV.userPos.left + "px", top: PRV.userPos.top + "px",
                                 right: "auto", bottom: "auto", margin: "0" });
      };
      const up = () => { document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); PRV.save(); };
      document.addEventListener("mousemove", move);
      document.addEventListener("mouseup", up);
    });
    head.addEventListener("dblclick", e => {
      if (e.target.closest(INERT)) return;
      PRV.userPos = null;
      Object.assign(o.style, { left: "16px", right: "16px", top: "auto", bottom: "16px", margin: "0 auto" });
      // A double-click fires mousedown/mouseup first, and that `up` handler has
      // already written the floating position we are discarding. Without this the
      // panel re-docks on screen and jumps back out on the next reload.
      PRV.save();
    });
    if (PRV.userPos)
      Object.assign(o.style, { left: PRV.userPos.left + "px", top: PRV.userPos.top + "px",
                               right: "auto", bottom: "auto", margin: "0" });

    // One resize handler for every grip. `data-v` means it drags height, `data-h`
    // ("l"/"r") means it drags width, and a corner simply carries both — which is
    // all a corner grip is. Three near-identical handlers had already drifted
    // apart once, so they are one.
    o.querySelectorAll("[data-v],[data-h]").forEach(g => g.addEventListener("mousedown", e => {
      e.preventDefault();
      const list = document.getElementById("prv-notes");
      const startY = e.clientY, startX = e.clientX;
      const startH = list ? list.getBoundingClientRect().height : 0;
      const startW = o.getBoundingClientRect().width;
      const vd = g.getAttribute("data-v");            // "up" | "down" | null
      const vert = !!vd;
      const down = vd === "down";
      const side = g.getAttribute("data-h");
      // Docked, the panel hangs off the viewport bottom, so a bottom grip has
      // nowhere to grow into — it would silently resize upward instead, away from
      // the edge being dragged. Cut it loose at exactly its current position and
      // the normal top-anchored geometry applies.
      if (down && !PRV.userPos) {
        const b = o.getBoundingClientRect();
        PRV.userPos = { left: b.left, top: b.top };
        Object.assign(o.style, { left: b.left + "px", top: b.top + "px",
                                 right: "auto", bottom: "auto", margin: "0" });
      }
      const box = o.getBoundingClientRect();
      const startTop = box.top, startLeft = box.left, startBoxH = box.height;
      // Centred (margin:auto) means widening moves BOTH edges, so one edge has to
      // travel twice the pointer. Once dragged loose the panel is left-anchored
      // and that doubling would overshoot.
      const grow = PRV.userPos ? 1 : 2;
      const move = ev => {
        if (vert && list) {
          // Up-grips grow as the pointer rises, bottom-grips as it falls.
          const dy = down ? (ev.clientY - startY) : (startY - ev.clientY);
          PRV.userHeight = Math.max(60, Math.min(startH + dy, innerHeight * 0.8));
          list.style.maxHeight = PRV.userHeight + "px";
        }
        if (side) {
          const sign = side === "r" ? 1 : -1;
          PRV.userWidth = Math.max(480,
            Math.min(startW + sign * (ev.clientX - startX) * grow, innerWidth - 32));
          o.style.maxWidth = PRV.userWidth + "px";
        }
        // Docked, the panel hangs off `bottom`, so growing it raises the top edge
        // under your pointer — right by construction. Dragged loose it hangs off
        // `top` instead, and the same growth pushes the BOTTOM down while the edge
        // you are holding stays put. Pin the far edge back: the one you grabbed
        // should be the one that moves.
        if (PRV.userPos) {
          const r = o.getBoundingClientRect();
          // A top grip pins the bottom; a bottom grip pins the top, which the
          // top-anchored layout already does for free.
          if (vert && !down) PRV.userPos.top = startTop + (startBoxH - r.height);
          if (side === "l") PRV.userPos.left = startLeft + (startW - r.width);
          o.style.top = PRV.userPos.top + "px";
          o.style.left = PRV.userPos.left + "px";
        }
      };
      const up = () => { document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); PRV.save(); };
      document.addEventListener("mousemove", move);
      document.addEventListener("mouseup", up);
    }));
    if (PRV.userWidth) o.style.maxWidth = PRV.userWidth + "px";

    o.querySelectorAll("button[data-a]").forEach(b => b.addEventListener("click", e => {
      b.style.opacity = ".55"; setTimeout(() => (b.style.opacity = "1"), 160);
      handle(b.dataset.a, e.shiftKey);
    }));

    const input = o.querySelector("#prv-input");
    // Comment mode FREEZES its anchor when armed. It used to re-anchor on every
    // navigation, so arming on a suspect block, glancing at the next one, then
    // typing filed the note against the wrong lines — and the only warning was a
    // placeholder quietly changing. The anchor is now captured once and shown as
    // a chip you can dismiss, so the mode is visible rather than inferred.
    PRV.setCommentMode = on => {
      PRV.commentArm = !!on;
      if (on) PRV.commentAnchor = here();
      const chip = document.getElementById("prv-chip");
      const r = on ? rangeLabel(PRV.commentAnchor) : "";
      if (chip) {
        chip.style.display = on ? "" : "none";
        chip.innerHTML = on
          ? `commenting on <b>${esc(PRV.commentAnchor.path || "this PR")}</b>` +
            (r ? ` <b>${r}</b>` : "") + ` <span data-x="1" style="opacity:.7;padding-left:4px">&#10005;</span>`
          : "";
      }
      input.placeholder = on
        ? (r ? `Note on ${r} — Enter to save, Esc to cancel`
             : "Note on this file — Enter to save, Esc to cancel")
        : "Ask a question — Enter to send";
      input.style.borderColor = on ? "#f78166" : bd;
      if (on) input.focus();
    };
    input.addEventListener("keydown", e => {
      e.stopPropagation();
      if (e.key === "Escape") { PRV.setCommentMode(false); input.blur(); return; }
      if (e.key === "Enter" && input.value.trim()) {
        const text = input.value.trim(); input.value = "";
        if (PRV.commentArm) {
          const a = PRV.commentAnchor || here();   // frozen at arm time
          PRV.setCommentMode(false);
          PRV.addUserNote(PRV.i, text, a.from, a.to);
          push({ action: "comment", i: PRV.i, c: PRV.c, ni: a.ni,
                 path: a.path, from: a.from, to: a.to, text });
        } else {
          const a = here();
          // A question interrupts. Otherwise the agent answers over the top of
          // narration that is still running and you get two voices at once.
          PRV.stopAudio();
          PRV.addPendingQ(text);
          push({ action: "say", text, i: PRV.i, c: PRV.c, ni: a.ni,
                 path: a.path, from: a.from, to: a.to });
        }
      }
    });

    if (!PRV._keys) {
      PRV._keys = e => {
        if (!document.getElementById("prv-overlay")) return;
        if (/^(INPUT|TEXTAREA)$/.test(e.target.tagName) || e.target.isContentEditable) return;
        if (e.metaKey || e.ctrlKey || e.altKey) return;
        const map = { n: "next", b: "back", p: "play", r: "play", s: "play",
                      c: "comment", h: "fold", t: "script", x: "rate",
                      a: "auto", k: "silent" };
        // Shifted N/B skip the whole file rather than the next observation.
        if (e.key === "N" || e.key === "B")
          { e.preventDefault(); return handle(e.key === "N" ? "ffwd" : "rwd"); }
        if (map[e.key]) { e.preventDefault(); handle(map[e.key]); }
      };
      document.addEventListener("keydown", PRV._keys, true);
    }
    PRV.setSilent(PRV.silent); PRV.setFold(PRV.folded);
    PRV.setScript(!!PRV.showScript); PRV.setRate(PRV.rate, false);
    return true;
  };

  const handle = (a, whole = false) => {
    if (a === "fold") return void PRV.setFold(!PRV.folded);
    if (a === "auto") return void PRV.setAuto(!PRV.auto);
    if (a === "silent") return void PRV.setSilent(!PRV.silent);
    if (a === "script") return void PRV.setScript();
    if (a === "rate") return void PRV.cycleRate(whole);   // shift = step back
    // Whole-file jumps, regardless of how many gates are left in this one.
    if (a === "close") return void PRV.unmount();
    if (a === "reopen") { PRV.done = false; render(); PRV.setFold(PRV.folded); return; }
    if (a === "ffwd") {
      if (PRV.i + 1 >= PRV.segments.length) { PRV.finish(); return push({ action: "end" }); }
      PRV.go(PRV.i + 1, 0, true); return;
    }
    if (a === "rwd") { if (PRV.i > 0) PRV.go(PRV.i - 1, 0, true); return; }
    if (a === "comment") return void PRV.setCommentMode(true);
    // Prev/Next walk observations; shift promotes them to whole-file jumps.
    // Explicit navigation always speaks — pressing Next IS the manual advance
    // control, so it must not be silenced by autoplay being off.
    if (a === "next") {
      if (whole) {
        if (PRV.i + 1 >= PRV.segments.length) { PRV.finish(); return push({ action: "end" }); }
        PRV.go(PRV.i + 1, 0, true); return;
      }
      const nb = PRV.nextBeat();
      if (!nb) { PRV.finish(); return push({ action: "end" }); }
      PRV.goBeat(nb.i, nb.c, true); return;   // goBeat emits position itself
    }
    if (a === "back") {
      if (whole) { if (PRV.i > 0) PRV.go(PRV.i - 1, 0, true); return; }
      const pb = PRV.prevBeat();
      if (pb) PRV.goBeat(pb.i, pb.c, true);
      return;
    }
    if (a === "stop") {
      PRV.stopAudio();
      // Kill agent-side playback too, without waking the agent — this is what makes
      // Stop instant even when the agent (not the page) is the one speaking.
      if (PRV.linked) PRV.bridge(PRV.server + "/stop", { method: "POST", body: "{}" });
      else push({ action: "stop" });
      return;
    }
    if (a === "play") {
      if (PRV.playing) return void PRV.pauseAudio();
      if (PRV.paused) return void PRV.resumeAudio();   // continue, never restart
      // Play NEVER advances. It used to jump to the next observation once this
      // one had finished, which made ▶ silently mean "go forward" and duplicated
      // Next sitting two controls away. One verb each: Play speaks what you are
      // looking at, Next moves you.
      PRV.playChunk(PRV.i, PRV.c, true).then(ok => { if (!ok) push({ action: "repeat" }); });
      return;
    }
    push({ action: a });                       // repeat, stop
  };

  // Collapse to just the header row — role, notes, input and progress hidden.
  PRV.setFold = f => {
    PRV.folded = !!f;
    ["prv-role", "prv-notes", "prv-input", "prv-progress"].forEach(id => {
      const e = document.getElementById(id);
      if (e) e.style.display = PRV.folded || PRV.done ? "none" : "";
    });
    // These two are conditional, so unfolding must not simply reveal them.
    const dn = document.getElementById("prv-done");
    if (dn) dn.style.display = PRV.folded || !PRV.done ? "none" : "";
    const sc = document.getElementById("prv-script");
    if (sc) sc.style.display = PRV.folded || !PRV.showScript || PRV.done ? "none" : "";
    const ch = document.getElementById("prv-chip");
    if (ch) ch.style.display = PRV.folded || !PRV.commentArm ? "none" : "";
    const b = document.getElementById("prv-fold");
    if (b) { b.textContent = PRV.folded ? "\u25B8" : "\u25BE"; b.dataset.tip = PRV.folded ? "expand (h)" : "collapse (h)"; }
    return PRV.folded;
  };

  // AUTO — who advances the cursor: the timer, or you. With it off you still
  // hear every observation; you just decide when the next one starts. Default
  // off, so nothing speaks while the review is still being written.
  //
  // Switching it off mid-walk only cancels the pending advance; the observation
  // being spoken finishes and the walk parks at its gate. Cutting the audio is
  // what pause is for, and conflating the two made turning autoplay off feel
  // like a stop button.
  //
  // `PRV.auto` is the user's PREFERENCE. Silence suspends it rather than
  // clearing it — autoOn() is the effective value — so unmuting gives them back
  // the setting they had rather than a surprise.
  PRV.setAuto = on => {
    const was = autoOn();
    PRV.auto = !!on;
    clearTimeout(PRV._chain);
    const b = document.getElementById("prv-auto");
    if (b) {
      b.dataset.on = autoOn() ? "1" : "0";
      b.style.opacity = PRV.silent ? ".45" : "";
      b.dataset.tip = PRV.silent
        ? "suspended while muted — there is no narration to advance along (a)"
        : autoOn() ? "autoplay ON — hands-free: plays, pauses, advances (a)"
                   : "autoplay OFF — one observation at a time, you advance (a)";
    }
    // Switching it on picks the walk back up from wherever the cursor parked.
    if (!was && autoOn() && !PRV.playing) {
      const nb = PRV._done ? PRV.nextBeat() : { i: PRV.i, c: PRV.c };
      if (nb) PRV.goBeat(nb.i, nb.c, true);
    }
    PRV.syncPlayBtn();
    PRV.save();
    return PRV.auto;
  };

  // MUTE — nothing is spoken, and everything else still works. Next and clicking
  // a block move the cursor, light the diff lines and swap the transcript; they
  // just say nothing. This is the read-it-yourself mode, and it is a separate
  // switch from auto because navigating deliberately forces playback past an
  // autoplay-off — which left no way to be quiet.
  //
  // Autoplay is suspended while muted rather than merely ignored: without audio
  // there is no duration to pace the walk by, so it could not advance anyway.
  // Better a dimmed button that says why than one that silently does nothing.
  PRV.setSilent = on => {
    PRV.silent = !!on;
    if (PRV.silent) PRV.stopAudio();
    const b = document.getElementById("prv-silent");
    if (b) {
      b.dataset.on = PRV.silent ? "1" : "0";
      b.dataset.tip = PRV.silent
        ? "muted — reading only; Next and clicking a block still move you (k)"
        : "mute the narration and just read (k)";
    }
    PRV.setAuto(PRV.auto);          // re-evaluates the pair and relabels both
    PRV.save();
    return PRV.silent;
  };

  // Click-to-zoom for note charts: full-screen lightbox, Esc or click closes.
  PRV.zoomSvg = svgHtml => {
    document.getElementById("prv-zoom")?.remove();
    const d = dark();
    const z = document.createElement("div");
    z.id = "prv-zoom";
    z.style.cssText = "position:fixed;inset:0;z-index:2147483647;background:rgba(0,0,0,.72);" +
      "display:flex;align-items:center;justify-content:center;cursor:zoom-out;backdrop-filter:blur(3px)";
    z.innerHTML = `<div style="background:${d ? "#161b22" : "#fff"};color:${d ? "#e6edf3" : "#1f2328"};` +
      `border-radius:12px;padding:30px;max-width:94vw;max-height:90vh;overflow:auto">${svgHtml}</div>`;
    const svg = z.querySelector("svg");
    if (svg) { svg.style.width = "min(1400px, 90vw)"; svg.style.height = "auto"; svg.removeAttribute("height"); }
    const close = () => { z.remove(); document.removeEventListener("keydown", esc, true); };
    const esc = e => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
    z.addEventListener("click", close);
    document.addEventListener("keydown", esc, true);
    document.body.appendChild(z);
    return true;
  };

  // ---- segments & notes --------------------------------------------------
  const render = () => {
    const s = PRV.segments[PRV.i]; if (!s) return;
    // Re-authoring can shrink a file's observation count under the cursor.
    PRV.c = Math.max(0, Math.min(PRV.c, PRV.beatCount(PRV.i) - 1));
    const set = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
    set("prv-count", `${PRV.i + 1} / ${PRV.segments.length}`);
    set("prv-path", s.path); set("prv-stat", s.stat || "");
    const t = document.getElementById("prv-tier");
    if (t) {
      const ready = (s.notes || []).length > 0;
      t.textContent = ready ? (TIERS[s.tier] || "") : "\u23F3";
      t.title = ready ? (s.tier || "") : "not authored yet";
    }
    const bar = document.getElementById("prv-bar");
    if (bar) {
      let done = PRV.c + 1, total = 0;
      PRV.segments.forEach((_, k) => {
        const n = PRV.beatCount(k);
        total += n;
        if (k < PRV.i) done += n;
      });
      bar.style.width = Math.round((done / Math.max(1, total)) * 100) + "%";
      const prog = document.getElementById("prv-progress");
      if (prog) prog.dataset.tip = `${done} of ${total} observations`;
    }
    const dp = document.getElementById("prv-depth");
    if (dp) {
      dp.style.display = PRV.depth === "guided" ? "none" : "";
      dp.textContent = PRV.depth;
      dp.dataset.tip = PRV.depth === "architect"
        ? "architect \u2014 each file explained from the system level; you read the lines"
        : "focused \u2014 close read on the risky files, higher lens elsewhere";
    }
    const fc = document.getElementById("prv-flags");
    if (fc) {
      const n = PRV.flagCount();
      fc.style.display = n ? "" : "none";
      fc.innerHTML = `&#9873; ${n}`;
      fc.dataset.tip = `${n} flagged point${n === 1 ? "" : "s"} — click to visit the next`;
    }
    PRV.syncPlayBtn();
    const nb = document.querySelector('#prv-overlay button[data-a="next"]');
    if (nb) {
      // Done only when there is genuinely nothing left. Keying this on "last
      // file" predates gates: entering the final file relabelled the button
      // while six observations were still ahead of it, so it read as an exit
      // and stopped being used to walk them.
      const last = !PRV.nextBeat();
      nb.innerHTML = last ? "Done &#10003;" : "Next &rsaquo;";
      nb.dataset.tip = last ? "finish: summary, then your drafted comments"
                            : "next observation (n)";
      nb.style.background = last ? "#1f6feb" : "#238636";
      nb.style.borderColor = last ? "#388bfd" : "#2ea043";
    }
    const role = document.getElementById("prv-role");
    if (role) {
      // While files are still being authored, say so and show progress — the user
      // must never wonder whether it is working or stuck.
      const ready = PRV.segments.filter(x => (x.notes || []).length).length;
      const hasAudio = PRV.hasAudio(PRV.i, 0);
      const prep = ready < PRV.segments.length
        ? `<span style="opacity:.75">\u23F3 preparing \u2014 <b>${ready}</b> of ${PRV.segments.length} files ready\u2026 you can browse now</span>`
        : (hasAudio && !PRV._playedAny
            ? `<span style="color:#3fb950">\u2713 ready \u2014 press <b>Play</b>${autoOn() ? " (autoplay on)" : ""}</span>`
            : "");
      const body = s.role ? md(s.role) : "";
      role.innerHTML = [body, prep].filter(Boolean).join('<br>');
      role.style.display = role.innerHTML ? "" : "none";
    }
    const list = document.getElementById("prv-notes"); if (!list) return;
    list.style.maxHeight = PRV.userHeight ? PRV.userHeight + "px" : (s.sha ? "200px" : "60vh");
    list.innerHTML = "";
    (s.notes || []).forEach((n, ni) => {
      const card = document.createElement("div");
      card.className = "prv-note";
      card.dataset.ni = ni;
      card.style.cssText = `display:flex;gap:10px;align-items:flex-start;padding:9px 11px;` +
        `cursor:pointer;font-size:12.5px;line-height:1.5;` +
        `background:${n.byUser ? "rgba(31,111,235,.14)" : "rgba(110,118,129,.10)"};` +
        `border-left:3px solid ${n.byUser ? "#1f6feb" : n.q ? "#238636" : "#6e7681"}`;
      const range = n.from ? `<span style="opacity:.6;font-family:ui-monospace,monospace;font-size:11px;white-space:nowrap">L${n.from}${n.to && n.to !== n.from ? "–" + n.to : ""}</span>` : "";
      const svg = n.svg ? `<div class="prv-svg" data-zoom="1" title="click to enlarge" style="margin-top:6px;overflow-x:auto;cursor:zoom-in">${n.svg}</div>` : "";
      const q = n.q ? `<div style="font-weight:600;margin-bottom:5px;padding:3px 9px;border-radius:6px;background:rgba(31,111,235,.16);border-left:3px solid #1f6feb;display:inline-block">${md(n.q)}</div>` : "";
      const body = n.pending
        ? `<div style="padding-left:12px;opacity:.55;font-style:italic">&#8627; ${n.digPending ? "digging into this file" : "thinking"}&hellip;</div>`
        : n.q ? `<div style="padding-left:12px;opacity:.92">&#8627; ${md(n.text)}</div>` : md(n.text);
      if (n.flag) card.dataset.flag = "1";
      const flag = n.pending ? "" :
        `<span class="prv-act prv-flag" data-flag-btn title="${n.flag
          ? "flagged for follow-up — click to clear"
          : "flag this point for follow-up"}">&#9873;</span>`;
      card.innerHTML = `${range}<span style="flex:1">${q}${body}</span>${n.pending ? "" : svg ? svg : ""}${flag}` +
        (n.byUser ? `<span data-x="${ni}" title="remove" style="opacity:.55;padding:0 4px;font-weight:600">&#10005;</span>` : "");
      card.addEventListener("click", e => {
        const zoomBox = e.target.closest && e.target.closest(".prv-svg");
        if (zoomBox && n.svg) { e.stopPropagation(); return PRV.zoomSvg(n.svg); }
        // Flag rides above the play-this-block click, so marking one for later
        // never moves the narration off what you are listening to.
        if (e.target.closest && e.target.closest("[data-flag-btn]")) {
          e.stopPropagation();
          n.flag = !n.flag;
          render();
          PRV.save();
          return push({ action: "flag", i: PRV.i, ni, on: !!n.flag,
                        path: s.path, from: n.from, to: n.to, text: n.text });
        }
        if (e.target.dataset.x != null) {
          s.notes.splice(+e.target.dataset.x, 1); render();
          return push({ action: "comment", i: PRV.i, text: null, removed: true });
        }
        // Clicking a block is the direct way to reach an observation: move the
        // cursor there and speak it. Cards with no narration of their own (user
        // comments, Q&A) have no gate to jump to, so they just light their lines.
        const ci = chunksOf(s).findIndex(k => k.ni === ni);
        if (ci >= 0) return void PRV.goBeat(PRV.i, ci, true);
        if (n.from) PRV.showNote(PRV.i, ni);
      });
      list.appendChild(card);
    });
    markActive();
    renderScript();
  };

  // Ring the card the narrator is on, and keep it in view — with gates the panel
  // has to show WHERE in the file the voice is, not just which file.
  const markActive = () => {
    const k = chunksOf(PRV.segments[PRV.i])[PRV.c];
    const ni = k ? k.ni : -1;
    document.querySelectorAll("#prv-notes .prv-note").forEach(el => {
      const on = ni >= 0 && +el.dataset.ni === ni;
      el.classList.toggle("prv-now", on);
      if (on) el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  };

  // ---- transcript ---------------------------------------------------------
  // Kokoro returns audio and nothing else — no token timestamps — so word timing
  // is derived from the one hard number we have, the chunk's measured duration.
  // Weight each word by its length plus the gap after it, and buy extra time at
  // punctuation, where the voice actually pauses. Error accumulates only within
  // a chunk, and a chunk is one observation, so it never drifts far enough to
  // point at the wrong sentence.
  const wordTimes = (text, dur) => {
    const words = [];
    const re = /\S+/g;
    let m;
    while ((m = re.exec(text))) words.push(m[0]);
    if (!words.length || !dur) return [];
    const weights = words.map(w => {
      let x = w.length + 1.6;                       // letters, plus the gap after
      if (/[,;:—–]["')\]]?$/.test(w)) x += 3.2;   // short breath
      else if (/[.!?]["')\]]?$/.test(w)) x += 6.0;          // full stop, longer
      return x;
    });
    const total = weights.reduce((a, b) => a + b, 0);
    let acc = 0;
    return words.map((w, k) => {
      const start = (acc / total) * dur;
      acc += weights[k];
      return { w, start };
    });
  };

  PRV._words = [];
  PRV._wk = -1;
  PRV._wEl = null;
  // Playback position, in file seconds. Defined before any play so fullSecs()
  // never arrives at NaN and silently drops the whole word table.
  PRV._at0 = PRV._at0 || 0;      // where this launch started in the file
  PRV._at = PRV._at || 0;        // where a pause left off
  PRV._dur = PRV._dur || 0;      // wall-clock remaining when it started
  PRV._full = PRV._full || 0;    // the file's own length
  const markWord = k => {
    if (PRV._wEl) { PRV._wEl.style.background = ""; PRV._wEl.style.borderRadius = ""; }
    const box = document.getElementById("prv-script");
    const el = box && box.querySelector(`span[data-w="${k}"]`);
    if (el) {
      el.style.background = "rgba(247,129,102,.32)";
      el.style.borderRadius = "3px";
      el.scrollIntoView({ block: "nearest" });     // only scrolls when out of view
    }
    PRV._wEl = el || null;
  };

  // Word times live in FILE seconds, not wall-clock, so they survive both a
  // resume part-way in and a speed change. Anything computing them against the
  // remaining duration squeezes the whole sentence into what is left and starts
  // over from word one — which is exactly what a resumed chunk looked like.
  const fullSecs = () => PRV._full || (PRV._dur * PRV.rate + PRV._at0);
  const armWords = () => {
    const k = chunksOf(PRV.segments[PRV.i])[PRV.c];
    PRV._words = k ? wordTimes(k.text, fullSecs()) : [];
  };

  // Server-side playback gives no timeupdate, so position is wall-clock since
  // /play returned, converted back to file time by the rate and the start
  // offset. Players do not drift; a stalled tab will, and it re-syncs next chunk.
  const walk = () => {
    if (!PRV.playing || !PRV._words.length) return void (PRV._raf = 0);
    const el = PRV._at0 + ((performance.now() - PRV._t0) / 1000) * PRV.rate;
    let k = PRV._wk;
    while (k + 1 < PRV._words.length && PRV._words[k + 1].start <= el) k++;
    if (k !== PRV._wk) { PRV._wk = k; markWord(k); }
    PRV._raf = requestAnimationFrame(walk);
  };
  PRV.stopWalk = () => {
    if (PRV._raf) cancelAnimationFrame(PRV._raf);
    PRV._raf = 0;
    if (PRV._wEl) { PRV._wEl.style.background = ""; PRV._wEl.style.borderRadius = ""; PRV._wEl = null; }
    PRV._wk = -1;
    return true;
  };

  // The text of the observation currently under the cursor, one span per word.
  // Rendered whether or not audio is playing — at a gate it is what you read.
  PRV._scriptKey = null;
  const renderScript = () => {
    const box = document.getElementById("prv-script");
    if (!box) return;
    box.style.display = PRV.showScript && !PRV.folded ? "" : "none";
    if (!PRV.showScript) return;
    const k = chunksOf(PRV.segments[PRV.i])[PRV.c];
    // autoRefresh re-renders every few seconds; rebuilding the spans under a
    // running walk would drop the highlight and detach the node it tracks. Only
    // touch the DOM when the text actually changed.
    const key = `${PRV.i}:${PRV.c}:${k ? k.text : ""}`;
    if (key === PRV._scriptKey) return;
    PRV._scriptKey = key;
    PRV._wEl = null; PRV._wk = -1;
    if (!k || !k.text) {
      box.innerHTML = '<span style="opacity:.5">nothing narrated for this one yet</span>';
      PRV._words = [];
      return;
    }
    const words = k.text.match(/\S+/g) || [];
    box.innerHTML = words.map((w, idx) =>
      `<span data-w="${idx}" style="transition:background .12s">${esc(w)}</span>`).join(" ");
    // Timing needs the measured duration, which only /play knows. Until then the
    // text just sits there readable; playChunk fills the times in when it starts.
    PRV._words = PRV.playing ? wordTimes(k.text, fullSecs()) : [];
  };
  // Narration speed. The server time-stretches with ffmpeg's atempo rather than
  // resampling, so Lewis keeps his pitch — resampling to 2x would raise him a
  // full octave. The audio itself is never re-synthesised; only playback changes.
  PRV.RATES = [1, 1.25, 1.5, 1.75, 2];
  PRV.rate = PRV.rate || 1;
  PRV.setRate = (r, restart = true) => {
    const changed = r !== PRV.rate;
    const was = PRV.rate;               // the offset must be scaled by the OLD rate
    PRV.rate = r;
    const b = document.querySelector('#prv-overlay button[data-a="rate"]');
    if (b) {
      b.innerHTML = String(r) + "&times;";
      b.dataset.on = r === 1 ? "0" : "1";
      b.dataset.tip = `narration speed ${r}× — click to cycle (x)`;
    }
    // Carry on from where the voice actually is, at the new speed. Restarting
    // the observation meant bumping to 1.5x to get through the rest faster made
    // you re-hear the sentence you had just heard. Skipped on a re-mount, which
    // re-applies the same rate and must not interrupt anything.
    if (restart && changed && PRV.playing) {
      const at = PRV._at0 + Math.max(0, (performance.now() - PRV._t0) / 1000) * was;
      PRV.playChunk(PRV.i, PRV.c, true, at);
    }
    return r;
  };
  PRV.cycleRate = (back = false) => {
    const n = PRV.RATES.length, i = PRV.RATES.indexOf(PRV.rate);
    return PRV.setRate(PRV.RATES[((back ? i - 1 : i + 1) + n) % n] || 1);
  };
  const flagStaleRate = () => {
    const b = document.querySelector('#prv-overlay button[data-a="rate"]');
    if (!b) return;
    b.dataset.tip = "speed needs a newer review server — restart it";
    b.style.borderColor = "#f78166";
    setTimeout(() => (b.style.borderColor = ""), 4000);
  };

  PRV.showScript = !!PRV.showScript;        // opt-in; survives a re-mount
  PRV.setScript = on => {
    PRV.showScript = on == null ? !PRV.showScript : !!on;
    PRV._scriptKey = null;                  // a toggle always redraws
    const b = document.querySelector('#prv-overlay button[data-a="script"]');
    if (b) {
      b.dataset.on = PRV.showScript ? "1" : "0";
      b.dataset.tip = PRV.showScript ? "hide the narration text (t)"
                                     : "show the narration text and follow it word by word (t)";
    }
    renderScript();
    if (PRV.showScript && PRV.playing) {
      const k = chunksOf(PRV.segments[PRV.i])[PRV.c];
      if (k) { armWords(); if (!PRV._raf) PRV._raf = requestAnimationFrame(walk); }
    }
    return PRV.showScript;
  };

  // Point everything at one observation: its lines in the diff, its card in the
  // panel. Replaces spreading the note ranges evenly across the file's duration,
  // which was only ever a guess at where the voice had got to.
  const aimAt = (i, c) => {
    const s = PRV.segments[i]; if (!s) return;
    const k = chunksOf(s)[c];
    if (i === PRV.i) { markActive(); renderScript(); }
    if (!k || !s.sha) return;
    if (k.from) PRV.highlight(s.sha, k.from, k.to || k.from);
  };

  PRV.load = (segments, startAt = 0) => {
    PRV.segments = segments;                    // replace, never append
    PRV.c = 0;
    PRV.go(startAt);
    return { loaded: segments.length };
  };

  // Incremental update of ONE segment — the progressive-authoring path. Merges
  // only the fields given; never touches position, never disturbs other segments,
  // and clears any pending dig card since results have arrived.
  PRV.fill = (i, patch = {}) => {
    const s = PRV.segments[i];
    if (!s) return { ok: false, why: "no such segment" };
    for (const k of ["role", "tier", "stat", "speech", "path", "sha"])
      if (patch[k] != null) s[k] = patch[k];
    if (Array.isArray(patch.notes)) {
      const mine = (s.notes || []).filter(n => n.byUser);   // keep user's own cards
      // A flag is the user's judgement, not the agent's content, so it must
      // survive a re-author. Keyed by text: indexes shift when notes are rewritten.
      const flags = new Set((s.notes || []).filter(n => n.flag).map(n => n.text));
      s.notes = patch.notes.map(n => flags.has(n.text) ? { ...n, flag: true } : n)
                           .concat(mine);
    } else if (patch.text != null) {
      (s.notes = s.notes || []).push({ text: patch.text, from: patch.from, to: patch.to });
    }
    if (s.notes) s.notes = s.notes.filter(n => !n.digPending);
    if (i === PRV.i) { render(); if (patch.from) PRV.highlight(s.sha, patch.from, patch.to || patch.from); }
    return { ok: true, i, notes: (s.notes || []).length };
  };

  PRV.go = (i, c = 0, play = false) => {
    if (i < 0 || i >= PRV.segments.length) return { ok: false, i: PRV.i };
    PRV.i = i; PRV.c = Math.max(0, Math.min(c, PRV.beatCount(i) - 1));
    PRV._done = false;
    clearTimeout(PRV._chain);
    if (!document.getElementById("prv-overlay")) PRV.mount();   // survive SPA re-render
    render();
    const s = PRV.segments[i];
    if (!s.sha) { PRV.clearHighlight(); }
    else {
      const file = document.getElementById("diff-" + s.sha);
      if (file) {
        file.scrollIntoView({ block: "start", behavior: "smooth" });
        setTimeout(() => aimAt(i, PRV.c), 320);
      } else { PRV.clearHighlight(); push({ action: "notrendered", i }); }
    }
    PRV.stopAudio();
    PRV.save();
    PRV.playChunk(i, PRV.c, play).then(played =>
      push({ action: "position", i, c: PRV.c, played, why: played ? null : PRV.why }));
    return { ok: true, i, c: PRV.c, overview: !s.sha };
  };

  // Move the observation cursor. Within a file this is cheap — no scroll, no
  // re-anchor, just re-aim and speak. Crossing a file boundary delegates to go().
  PRV.goBeat = (i, c, play = true) => {
    if (i !== PRV.i) return PRV.go(i, c, play);
    if (i < 0 || i >= PRV.segments.length) return { ok: false, i: PRV.i };
    PRV.c = Math.max(0, Math.min(c, PRV.beatCount(i) - 1));
    // Skipping mid-sentence has to silence the current gate first, exactly as
    // go() does when it crosses a file. The server enforces this too, but the
    // local state (button glyph, word walk) has to follow immediately.
    PRV.stopAudio();
    PRV._done = false;
    clearTimeout(PRV._chain); clearTimeout(PRV._endTimer);
    render();
    aimAt(i, PRV.c);
    pushPosition();
    PRV.save();
    if (play) PRV.playChunk(i, PRV.c, true);
    return { ok: true, i, c: PRV.c };
  };

  PRV.showNote = (si, ni) => {
    const s = PRV.segments[si], n = s && (s.notes || [])[ni];
    if (!n || !n.from) return false;
    return PRV.highlight(s.sha, n.from, n.to || n.from);
  };

  PRV.addUserNote = (i, text, from = null, to = null) => {
    const s = PRV.segments[i]; if (!s) return false;
    (s.notes = s.notes || []).push({ from, to, text, byUser: true });
    if (i === PRV.i) render();
    return true;
  };

  // A typed question pins itself immediately as a pending card; the agent's
  // answer fills that same card in place. Not collected by collectNotes.
  PRV.addPendingQ = q => {
    const s = PRV.segments[PRV.i]; if (!s) return false;
    (s.notes = s.notes || []).push({ q, text: null, pending: true });
    render();
    return true;
  };
  PRV.addAnswer = (i, q, text) => {
    const s = PRV.segments[i]; if (!s) return false;
    s.notes = s.notes || [];
    const hit = s.notes.find(n => n.pending && n.q === q) || s.notes.find(n => n.pending);
    if (hit) { hit.text = text; hit.pending = false; }
    else s.notes.push({ q, text });
    if (i === PRV.i) render();
    return true;
  };

  // Everything the user acted on: their own cards, plus any of yours they
  // flagged for follow-up.
  // The walk is over. Pressing Done used to only push an `end` event and leave
  // the bar exactly as it was, so it read as a dead button while the agent was
  // still working. The page closes itself out now, immediately and without
  // waiting for anything: what was collected, what happens next, and a way out.
  PRV.finish = () => {
    PRV.done = true;
    PRV.stopAudio();
    clearTimeout(PRV._chain);
    const notes = PRV.collectNotes();
    const mine = notes.filter(n => n.byUser).length;
    const flags = notes.filter(n => n.flag).length;
    const files = PRV.segments.filter(s => s.sha).length;
    const box = document.getElementById("prv-done");
    if (box) {
      const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
      box.innerHTML =
        `<div style="font-weight:600;font-size:13.5px;margin-bottom:5px">&#10003; Review complete</div>` +
        `<div style="font-size:12.5px;opacity:.85;line-height:1.5">` +
        `${plural(files, "file")} walked &middot; ${plural(mine, "comment")} of yours` +
        (flags ? ` &middot; ${plural(flags, "flagged point")}` : "") + `</div>` +
        `<div id="prv-status" style="font-size:12.5px;margin-top:8px;opacity:.75">` +
        `Wrapping up in the terminal &mdash; settling anything flagged, then your review to submit.</div>` +
        `<div style="margin-top:11px;display:flex;gap:6px">` +
        `<button data-a="close" data-primary="1">Close panel</button>` +
        `<button data-a="reopen">Back to the review</button></div>`;
      box.querySelectorAll("button[data-a]").forEach(b =>
        b.addEventListener("click", () => handle(b.dataset.a)));
    }
    render();
    PRV.setFold(PRV.folded);      // the show/hide rules live there
    return { files, comments: mine, flagged: flags };
  };
  // The agent narrates progress here while it submits, so the panel is never
  // a stale "wrapping up" once the work is actually done.
  PRV.setStatus = t => {
    const e = document.getElementById("prv-status");
    if (e) e.textContent = t;
    return !!e;
  };

  // ---- surviving a reload -------------------------------------------------
  // Segments come back from the server, but everything the USER did lived only
  // in this page object: where they were, what they flagged, how they had set
  // the panel up. A refresh — which GitHub also forces on some navigations —
  // threw all of it away. Keyed by PR path, so two PRs never share state.
  // Resolved lazily and guarded: reading location at load time would throw the
  // whole overlay away in any context that lacks it, and storage is a nicety.
  const storeKey = () => {
    try { return "prv:" + location.pathname.replace(/\/files.*$/, ""); }
    catch (_) { return "prv:unknown"; }
  };
  // Flags key on path + note text, not index: the agent re-authors notes and the
  // indexes shift under them, which is how they would silently reattach to the
  // wrong observation.
  const flagKeys = () => PRV.segments.flatMap(s =>
    (s.notes || []).filter(n => n.flag).map(n => s.path + "\u0000" + n.text));
  PRV.save = () => {
    try {
      localStorage.setItem(storeKey(), JSON.stringify({
        i: PRV.i, c: PRV.c, flags: flagKeys(), depth: PRV.depth,
        auto: PRV.auto, silent: PRV.silent, rate: PRV.rate, script: PRV.showScript,
        pos: PRV.userPos, w: PRV.userWidth, h: PRV.userHeight, at: Date.now()
      }));
    } catch (_) {}          // private mode, quota — never break the walk over it
    return true;
  };
  PRV.restore = () => {
    let d = null;
    try { d = JSON.parse(localStorage.getItem(storeKey()) || "null"); } catch (_) {}
    if (!d || Date.now() - (d.at || 0) > 7 * 864e5) return false;   // a week
    const want = new Set(d.flags || []);
    PRV.segments.forEach(s => (s.notes || []).forEach(n => {
      if (want.has(s.path + "\u0000" + n.text)) n.flag = true;
    }));
    if (d.depth) PRV.depth = d.depth;
    if (d.rate) PRV.rate = d.rate;
    PRV.auto = !!d.auto; PRV.silent = !!d.silent; PRV.showScript = !!d.script;
    PRV.userPos = d.pos || null;
    PRV.userWidth = d.w || null; PRV.userHeight = d.h || null;
    PRV._restored = { i: d.i || 0, c: d.c || 0 };
    return true;
  };

  PRV.collectNotes = () =>
    PRV.segments.flatMap(s => (s.notes || [])
      .filter(n => n.byUser || n.flag)
      .map(n => ({ path: s.path, from: n.from, to: n.to, text: n.text,
                   byUser: !!n.byUser, flag: !!n.flag })));
  PRV.flagged = () => PRV.collectNotes().filter(n => n.flag);

  // The user's own outstanding list, kept visible so they never have to ask the
  // agent "what did I flag?" — which is exactly what happened before this.
  // Clicking walks to the next flagged block, wrapping across files.
  PRV.flagCount = () =>
    PRV.segments.reduce((t, s) => t + (s.notes || []).filter(n => n.flag).length, 0);
  PRV.nextFlag = () => {
    const hits = [];
    PRV.segments.forEach((s, i) =>
      (s.notes || []).forEach((n, ni) => { if (n.flag) hits.push({ i, ni }); }));
    if (!hits.length) return null;
    return hits.find(h => h.i > PRV.i) || hits.find(h => h.i === PRV.i) || hits[0];
  };
  PRV.gotoFlag = () => {
    const h = PRV.nextFlag();
    if (!h) return false;
    const c = chunksOf(PRV.segments[h.i]).findIndex(k => k.ni === h.ni);
    if (h.i !== PRV.i) PRV.go(h.i, Math.max(0, c), false);
    else if (c >= 0) PRV.goBeat(h.i, c, false);
    return true;
  };

  // Local audio: fetch a pre-rendered narration through the bridge and play it
  // in-page. Returns true if playback started. Stop/mute/repeat become instant.
  PRV.gap = 2500;                       // pause between files in autoplay
  PRV.beatGap = 900;                    // shorter beat between observations
  PRV.stopAudio = () => {
    clearTimeout(PRV._chain); clearTimeout(PRV._endTimer);
    PRV.playing = false; PRV.paused = false;
    PRV.stopWalk();
    PRV._done = false;
    if (PRV.linked) PRV.bridge(PRV.server + "/stop", { method: "POST", body: "{}" });
    PRV.syncPlayBtn();
    return true;
  };

  // Pause holds the sentence where it is: the server SIGSTOPs the player, so
  // resuming continues mid-word instead of starting the observation over. The
  // page keeps the elapsed time, which is all that is needed to put the word
  // walk and the end-of-chunk timer back exactly where they were.
  PRV.pauseAudio = () => {
    if (!PRV.playing) return false;
    clearTimeout(PRV._chain); clearTimeout(PRV._endTimer);
    // Where the voice had reached, in file seconds — the offset a resume needs.
    // Clamp at 0: pausing during the lead-in means nothing has been said yet.
    PRV._at = PRV._at0 + Math.max(0, (performance.now() - PRV._t0) / 1000) * PRV.rate;
    PRV.playing = false; PRV.paused = true;
    if (PRV._raf) cancelAnimationFrame(PRV._raf);
    PRV._raf = 0;                              // freeze the lit word in place
    if (PRV.linked) PRV.bridge(PRV.server + "/stop", { method: "POST", body: "{}" });
    PRV.syncPlayBtn();
    return true;
  };
  // Resume re-launches the same file from the stored offset. A server too old to
  // accept `at` ignores it and starts over — a worse resume, never a broken one.
  PRV.resumeAudio = () => {
    if (!PRV.paused) return false;
    PRV.paused = false;
    return PRV.playChunk(PRV.i, PRV.c, true, PRV._at);
  };
  PRV.hasAudio = (i, c = 0) => PRV.ready.has(i + ":" + c);
  // The play button doubles as pause and as the gate release: keep it honest.
  PRV.syncPlayBtn = () => {
    const n = PRV.beatCount(PRV.i);
    const lab = document.getElementById("prv-beat");
    if (lab) {
      lab.textContent = n > 1 ? `${PRV.c + 1}/${n}` : "";
      lab.dataset.tip = `observation ${PRV.c + 1} of ${n} in this file`;
    }
    const b = document.querySelector('#prv-overlay button[data-a="play"]');
    if (!b) return;
    b.innerHTML = PRV.playing ? "&#10073;&#10073;" : "&#9654;";
    b.dataset.tip = PRV.playing ? "pause (p)"
      : PRV.paused ? "resume where it stopped (p)"
      : PRV._done ? "say this one again (p)"
      : n > 1 ? "play this observation (p)" : "play this file's narration (p)";
  };
  // Prefetch narration into a decoded <audio> element so playback is instant —
  // fetching over the bridge at press time costs a few hundred ms, which is exactly
  // the lag "pre-generated" audio is supposed to eliminate.

  // Playback lives on the server. GitHub's CSP media-src blocks blob: and data:,
  // so the page cannot play audio at all — but it is the same machine, so the
  // server plays through the speakers and returns the duration, which is all the
  // page needs to time highlights and chain the walk.
  PRV.playing = false;
  PRV._done = false;              // current observation has run all the way to its gate
  // `played:false` used to mean two very different things — "could not" and
  // "chose not to" — and the agent could not tell them apart, so it helpfully
  // spoke the narration itself every time the user navigated with autoplay off.
  // Every refusal now carries a reason, and only "not-rendered" is a fault.
  const bail = why => { PRV.why = why; return false; };
  PRV.playChunk = async (i, c = 0, force = false, at = 0) => {
    if (!PRV.linked) return bail("no-bridge");
    if (PRV.silent) return bail("muted");             // a deliberate choice
    if (!autoOn() && !force) return bail("autoplay-off");   // also deliberate
    clearTimeout(PRV._chain); clearTimeout(PRV._endTimer);
    const r = await PRV.bridge(PRV.server + "/play",
      { method: "POST", body: JSON.stringify({ i, c, rate: PRV.rate, at }) });
    let j = {};
    try { j = JSON.parse(r.text || "{}"); } catch (_) {}
    if (!j.ok) {
      PRV.playing = false; PRV.syncPlayBtn();
      return bail(/not rendered/.test(j.why || "") ? "not-rendered" : "play-failed");
    }
    // A slow bridge round trip can land after the user has already moved on.
    if (PRV.i !== i || PRV.c !== c) {
      PRV.bridge(PRV.server + "/stop", { method: "POST", body: "{}" });
      return false;
    }
    // A server older than the speed control ignores `rate` and echoes none back,
    // so the button would cycle while nothing changed. Say so rather than look
    // broken — the fix is restarting the review server.
    PRV.rateOk = j.rate != null;
    if (!PRV.rateOk && PRV.rate !== 1) PRV.setRate(1, false), flagStaleRate();
    PRV.playing = true; PRV.paused = false; PRV._done = false; PRV._playedAny = true;
    PRV.why = null;
    // _at0 is where in the FILE this launch started; _dur is what remains of
    // it in wall-clock. Both are needed to work out a later pause offset.
    // The player takes time to open the audio device before any sound comes out,
    // and /play returns the moment the process is spawned. Start the clock when
    // the VOICE starts, not when the process does — otherwise the transcript
    // highlight runs ahead of what you are hearing by that whole gap.
    PRV._lead = j.lead || 0;
    PRV._t0 = performance.now() + PRV._lead * 1000;
    PRV._at0 = j.at != null ? j.at : at;
    PRV._dur = j.duration || 3;
    PRV._full = j.full || PRV._dur;
    PRV.syncPlayBtn();
    aimAt(i, c);
    // Duration is only known now, so this is where the transcript gets its timing.
    PRV.stopWalk();
    if (PRV.showScript) {
      const k = chunksOf(PRV.segments[i])[c];
      if (k) { armWords(); PRV._raf = requestAnimationFrame(walk); }
    }

    armChunkEnd(PRV._dur + PRV._lead);
    return true;
  };
  const nextIsNewFile = () => { const n = PRV.nextBeat(); return !n || n.i !== PRV.i; };
  // Server has no callback, so time the end from the duration it reported.
  // Takes the REMAINING seconds, not the total, so a resume lands correctly.
  const armChunkEnd = remaining => {
    clearTimeout(PRV._endTimer);
    PRV._endTimer = setTimeout(() => {
      PRV.playing = false; PRV.paused = false; PRV._done = true;
      PRV.stopWalk(); PRV.syncPlayBtn();
      if (!autoOn()) return;                    // gated: park here, you advance
      PRV._chain = setTimeout(() => {
        if (!autoOn()) return;
        const nb = PRV.nextBeat();
        if (!nb) { PRV.finish(); return push({ action: "end" }); }
        PRV.goBeat(nb.i, nb.c, true);
      }, nextIsNewFile() ? (PRV.gap || 2000) : PRV.beatGap);
    }, Math.round(remaining * 1000) + 120);   // lead is accounted for by caller
  };
  // Kept for callers that speak a whole file rather than one observation.
  PRV.playSeg = (i, force = false) => PRV.playChunk(i, 0, force);

  // ---- agent side --------------------------------------------------------
  PRV.wait = (ms = 60000) => new Promise(res => {
    if (PRV.queue.length) return res(PRV.queue.shift());
    const t = setTimeout(() => { PRV.waiter = null; res({ action: "TIMEOUT" }); }, ms);
    PRV.waiter = ev => { clearTimeout(t); res(ev); };
  });
  PRV.drain = () => PRV.queue.splice(0, PRV.queue.length);

  // Self-refresh: while any segment is still unauthored, poll the server and merge.
  // This is what lets parallel authoring subagents publish without ever touching
  // the browser — they POST /segment/<i>, the page picks it up on its own.
  PRV.ready = new Set();          // "i:c" keys — which gates can actually play
  PRV.renderedFiles = 0;
  // What the AGENT owns in a segment. User notes and flags are excluded, so a
  // re-poll that finds no agent change touches nothing.
  const agentSig = s => JSON.stringify([
    s.role, s.speech, s.tier,
    (s.notes || []).filter(n => !n.byUser)
      .map(n => [n.from, n.to, n.text, n.speech, n.svg ? 1 : 0])]);
  PRV._sigs = PRV._sigs || {};

  PRV.autoRefresh = (ms = 4000) => {
    clearInterval(PRV._refresh);
    let tick = 0;
    PRV._refresh = setInterval(async () => {
      if (!PRV.linked || !PRV.segments.length) return;
      // Never stop. This used to clearInterval once every file was authored and
      // rendered, which is exactly when the interesting updates start arriving —
      // dig-ins, answers, follow-ups on a flag — and none of them showed up
      // without a page reload. Just slow down when there is nothing pending.
      const settled = !PRV.segments.some(s => !(s.notes || []).length) &&
                      PRV.renderedFiles >= PRV.segments.length;
      if (settled && (++tick % 2)) return;             // every other tick once quiet

      const st = await PRV.bridge(PRV.server + "/status");
      if (st.ok && st.text) {
        try {
          const j = JSON.parse(st.text);
          PRV.ready = new Set(j.renderedChunks || (j.renderedIdx || []).map(i => i + ":0"));
          PRV.renderedFiles = j.rendered || 0;
          render();
        } catch (_) {}
      }
      const r = await PRV.bridge(PRV.server + "/segments");
      if (!r.ok || !r.text) return;
      try {
        JSON.parse(r.text).forEach((incoming, i) => {
          const cur = PRV.segments[i];
          if (!cur) return;
          // Merge whenever the agent's content CHANGED — not only when the
          // segment was empty. Re-authoring an already-written file was the
          // other half of the same bug.
          const sig = agentSig(incoming);
          if (sig === PRV._sigs[i]) return;
          PRV._sigs[i] = sig;
          if (!(incoming.notes || []).length && !incoming.speech) return;
          PRV.fill(i, incoming);                       // position-safe, keeps user notes
        });
      } catch (_) {}
    }, ms);
    return true;
  };

  PRV.unmount = () => {
    clearInterval(PRV._refresh);
    PRV.clearHighlight();
    document.getElementById("prv-overlay")?.remove();
    document.getElementById("prv-style")?.remove();
    if (PRV._keys) document.removeEventListener("keydown", PRV._keys, true);
    delete window.__prv;
    return true;
  };

  return true;
})();
