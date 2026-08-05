# CrossTrans — Roadmap

> Active and upcoming work only. Completed items are archived in `ROADMAP_DONE.md`
> and summarized for users in `CHANGELOG.md`.
> Status legend: 📋 Planned (design pending) · 🔨 In progress · ✅ Done (archived)

---

## Active / Upcoming

| # | Item | Status | Notes |
|---|------|--------|-------|
| F0 | **Furigana engine** — `src/core/furigana.py`: structured `RubySegment` contract, invariant I1, fail-safe aligner, fugashi→pykakasi provider chain. Fixes 7 defects (okurigana span, homograph readings, `kakasi()` per-call rebuild, notation injection, multi-line ruby loss, digit-counter readings, split compounds). No UI change. | ✅ Done (2026-08-04) | 124 → 208 tests. See Decision 8 |
| F1 | **`RubyText` primitive** — `src/ui/ruby_text.py` as the single place ruby is drawn; `_render_furigana` is a delegate. Fixes the height unit bug (28px `height` unit vs 47px real ruby row), the popup height estimate, the wheel dead-zone over ruby frames, and the suppression of ruby for text holding `{`/`|`/`\`. Adds `get_plain()`. | ✅ Done (2026-08-05) | 208 → 257 tests. Popup verified pixel-identical by screenshot; height predictions match `count(..., 'ypixels')` exactly |
| F2 | **Popup fully ruby** — `popup_text` + replace preview; screenshot/OCR, grammar and merged results inherit it. Route the `.get()` at `quick_translate.py:1002` through `RubyText.get_plain()`; guard the custom-prompt `state='normal'` window. | 📋 Planned | I2 gate: no `.get()` on a ruby widget |
| F3 | **Main output + expanded window** — `trans_text` and `expanded_window` (make it read-only; nothing consumes its edits). Route `app.py:1248/1253/1269` and `expanded_window.py:112/161`. Fix "Open Translator" dropping readings (`app.py:443`). | 📋 Planned | |
| F4 | **Input Reading pane** — read-only collapsible `RubyText` under `original_text`; input box stays plain (I3). Refresh on debounced keystroke **and** the programmatic writes at `app.py:1168-1169` / `1330-1331`. Fix the `config.py:344` default fallback; reword `hotkey_tab.py:255`. | 📋 Planned | |
| F5 | **Dictionary result (8 fields)** — ruby on values only; keep the monospace label columns from `_align_dictionary_text`. Suppress ruby on field 5 (Pronunciation — the prompt deliberately asks for katakana). | 📋 Planned | |
| F6 | **Word chips** — `WordLabel` / `WordTag` become 2-row frames; update drag ghosts (`custom_word_boxes.py:424`, `dictionary_mode.py:548`) and the plain-inserted tokens at `dictionary_mode.py:271-275`. | 📋 Planned | |
| F7 | **Hardening** — `prewarm()` off-thread, `FURIGANA_*` constants, and an EXE guard in `build_exe.bat` (it currently verifies nothing; asserting `kanwadict4.db` is bundled is a 1-line, high-value check). | 📋 Planned | |

**Explicit non-goals** (documented, not oversights): toasts and the history *list* (`tk.Label` /
60-char truncations; converting history rows would break click-to-load), `tk.Listbox`,
`ttk.Entry` / `Combobox`, buttons, menus, `messagebox`, OS title bars and the tray menu — Tk
cannot embed widgets in any of these.

**Archiving note**: the finished F-rows stay in this table until F7 lands, then the whole F0–F7
block moves to `ROADMAP_DONE.md` as one item. They are the reference context the remaining
phases are written against (invariants, file/line targets), so splitting them out mid-feature
would cost more than it saves.

---

## Recently completed (see `ROADMAP_DONE.md` + `CHANGELOG.md`)

- **Rename** — storage identity aligned to CrossTrans (config dir, model cache, autostart registry key, DPAPI entropy); clean rename, no migration — breaking change: existing users re-enter API keys + manually clear the old autostart entry. See Decision 7 — ✅ Done (2026-07-02) [Unreleased]
- **G2** — Merged Translate-or-Fix on language hotkeys (one merged prompt; same-language text is grammar-fixed; no-censor on all translations; Win+Alt+G retired to opt-in) — ✅ Done (2026-07-01) [1.9.18]
- **G1** — Fix Grammar (Win+Alt+G hotkey + main-window button + settings toggle + tray entry) — ✅ Done (2026-06-30) [1.9.17]
- **R1** — Translation result cache (history-backed) + "Re-translate" button — ✅ Done
- **R2** — "Custom Prompt" editable-box freeform ask in Quick Translate popup — ✅ Done
- **R2-bug** — custom_prompt branch now embeds source text — ✅ Done
