# Teardown — mostly, do nothing

**Do not kill the server at wrap-up.** Everything here cleans up after itself, and
killing it costs the next review a cold start — the exact thing the warm worker exists
to prevent.

| What | Size | Who cleans it |
|---|---|---|
| narration audio | small | the session dir lives under `/tmp`; the OS sweeps it (measured: already 0 B) |
| the kokoro workers | **~525 MB each, up to 3** | **the server**, 10 min after the last synthesis — and `warm_synth` respawns the pool on demand |
| the server itself | a few MB | itself, after 2 h idle |
| the per-PR cache | ~20 MB a review | itself: newest 20 entries, nothing over 30 days |
| the audio cache | a few MB | unbounded today — clips keyed by narration text |

**Narration is cached by its own text**, not by the review it belongs to. The per-PR cache
is keyed on the head sha, so one new commit invalidated every clip even though nearly all
the narration was word-for-word identical; now pushing a commit only re-renders the chunks
whose text actually changed. Measured on six chunks: 3.3 s cold, **0.00 s** cached.

Synthesis also runs a small pool (up to 3) rather than one process, with intra-op threads
capped to `cores / workers`. Uncapped workers are *slower* than a single one — each tries
to take every core — and CoreML is slower still, since it supports 650 of the model's 2389
nodes and the graph splits into 109 partitions.

The cache under `~/.local/state/pr-voice-review/` is **deliberately** persistent — it is
what makes re-opening a PR instant instead of a full re-author. Never clear it as
housekeeping. If the user asks how, tell them the path and let them delete it.

Kill the server only when the user asks, or when you need it on different settings (a
different port, `--tts`, or `--chime`): `kill "$(cat "$D/server.pid")"`.
