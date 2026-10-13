# Visual review (screenshots)

**Do not route visual review through these dispatch agents.** Tested and it does not work reliably: the CLIs can each read an image when asked in a bare one-shot prompt, but inside a full review prompt they consistently deprioritise the screenshot and review the source instead — claude ignored an explicit "state the labels you see or say CANNOT_SEE_IMAGE" instruction, codex ignored a natively-attached `-i` image, and agy errored. There is no `--image` flag because one was built, measured, and found not to earn its complexity.

**Do it in the orchestrating session instead.** The agent running `/review-work` can read a screenshot directly and review it — no dispatch, no isolation flags, no per-backend routing. Capture with the project's `run` skill or browser tooling, look at the image, and fold the visual findings into the summary alongside the agents' source findings.

Use the dispatch agents for what they are good at — reasoning over source in parallel and independently — and keep the rendered judgement in-session where the image reliably lands.

The rest of this section documents what *was* verified, for whoever revisits this.

If you still want to try it from a dispatch agent, append the paths to the prompt file the same way Step 3 appends design docs — but treat a silent source-only review as the likely outcome and check whether the summary actually references the image.

What was verified, with a bare one-shot prompt (`"Read the image at X. What text appears?"`) — all four read a mock containing `Submit Order / Cancel / 3 items in cart` correctly:

| Backend | Vision | Notes |
|---|---|---|
| `claude` | ✅ | reads the path under `--permission-mode plan` as-is — the easiest choice |
| `agy` | ✅ | **needs `read_file(<path>)` in `~/.gemini/antigravity-cli/settings.json`**; headless soft-denies file reads even inside a trusted workspace |
| `codex` | ⚠️ | sees images via `-i` when invoked directly, but not reliably from a path in the prompt — prefer `claude` or `agy` |
| `pi` | ⚠️ | needs a vision model (`kimi-k3`; `glm-*`/`deepseek-*` are text-only) |
| `or` | ❌ | no tools at all |

The "do not run shell commands" line is load-bearing for `agy`: without it the model reaches for `python3 -c "from PIL import Image..."` to sample pixels, which needs `command` permission and is not actually looking at the image.

**A text-only model handed a screenshot path will review without it** and may still sound confident. Pick the backend deliberately — `claude` and `agy` are the reliable pair, and they cost no metered cash.
