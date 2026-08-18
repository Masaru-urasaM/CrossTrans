# CrossTrans — Roadmap

> Active and upcoming work only. Completed items are archived in `ROADMAP_DONE.md`
> and summarized for users in `CHANGELOG.md`.
> Status legend: 📋 Planned (design pending) · 🔨 In progress · ✅ Done (archived)

---

## Active / Upcoming

_No active items._

---

## Recently completed (see `ROADMAP_DONE.md` + `CHANGELOG.md`)

- **F0–F7 — Furigana everywhere** — hiragana readings above kanji on every surface that can show
  Japanese: quick-translate popup, main window, expanded view, the input Reading pane, the
  dictionary result window and the dictionary word chips. Render-time annotation, fail-safe
  aligner ("blank beats a wrong reading"), prewarmed off-thread, guarded at build time. 124 → 450
  tests. See Decision 8 — ✅ Done (2026-08-17) [Unreleased]
- **Rename** — storage identity aligned to CrossTrans (config dir, model cache, autostart registry key, DPAPI entropy); clean rename, no migration — breaking change: existing users re-enter API keys + manually clear the old autostart entry. See Decision 7 — ✅ Done (2026-07-02) [Unreleased]
- **G2** — Merged Translate-or-Fix on language hotkeys (one merged prompt; same-language text is grammar-fixed; no-censor on all translations; Win+Alt+G retired to opt-in) — ✅ Done (2026-07-01) [1.9.18]
- **G1** — Fix Grammar (Win+Alt+G hotkey + main-window button + settings toggle + tray entry) — ✅ Done (2026-06-30) [1.9.17]
- **R1** — Translation result cache (history-backed) + "Re-translate" button — ✅ Done
- **R2** — "Custom Prompt" editable-box freeform ask in Quick Translate popup — ✅ Done
- **R2-bug** — custom_prompt branch now embeds source text — ✅ Done
