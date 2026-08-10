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
| F2 | **Popup fully ruby** — the output box is a `RubyText`, so translating *into* Japanese finally shows readings; screenshot/OCR, grammar and merged results inherit it. Custom-prompt Send routed through `get_plain()` (it was sending a kanji-stripped prompt) and the box is flattened before editing (I3). Closes the F0 kanji-only gap for output via the target-language hint. | ✅ Done (2026-08-06) | 257 → 286 tests. Also fixed: ttkbootstrap was discarding the ruby colours app-wide, and the `furigana_enabled` default fallback |
| F3 | **Main output + expanded window** — `trans_text` and the expanded view are `RubyText`; the main window had never shown readings at all, so "Open Translator" dropped them. Expanded view is now read-only (a disabled `tk.Text` still selects and copies). Copy, Expand, the expanded Copy button and its character counter all routed through `get_plain()`. | ✅ Done (2026-08-07) | 286 → 307 tests. Also fixed: measurements ignored the widget's real `spacing1`/`spacing3` |
| F4 | **Input Reading pane** — read-only collapsible `RubyText` under `original_text`, shown by default; the input box stays plain (I3). One debounced `<<Modified>>` binding replaced the planned per-call-site refreshes: it also covers paste, drag-and-drop, undo and the programmatic rewrites. Dim placeholder instead of mirroring unannotatable text. `hotkey_tab.py` toggle description reworded. | ✅ Done (2026-08-07) | 307 → 331 tests, each mutation-checked. New config key `furigana_reading_pane` (collapse state, default expanded) |
| F5 | **Dictionary result (8 fields)** — new `src/ui/dictionary_render.py` run model: ruby on values only, monospace columns intact, field 5 (Pronunciation) suppressed by label *and* number. Word highlighting moved from post-insert `Text.search()` (which cannot find an annotated word) to the run itself, so a looked-up word is coloured *and* annotated. Uses the result's own `**Source Language**` field as the hint, per entry — closing the kanji-only gap for bare-kanji lookups. | ✅ Done (2026-08-10) | 331 → 376 tests, each mutation-checked. Pre-existing ~154px height over-estimate reported, not changed |
| F6 | **Word chips** — `WordLabel` / `WordTag` become 2-row `RubyRow` grids, ghosts included. Readings come from `annotate_tokens()` on the whole line, since the tokenizer splits compounds (日本 alone reads にっぽん, not にほん) — a token cutting a reading stays bare. Chips/tags insert with `align='baseline'` (centre was 7px out) and the custom box grows so a reading is not clipped. | ✅ Done (2026-08-10) | 376 → 422 tests, all mutation-checked. Also fixed: wheel dead zone over every chip, and a `TclError` reachable from the drop-line motion handler |
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
