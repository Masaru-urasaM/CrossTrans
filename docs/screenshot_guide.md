# Screenshot Capture Guide for README

This guide explains how to capture professional screenshots for CrossTrans README.md.

---

## Recommended Tools

- **Win+Shift+S** (Snipping Tool, built into Windows 10/11) — fast and convenient
- **ShareX** (free, open source) — more options, supports annotations

## Image Specifications

| Parameter | Value |
|-----------|-------|
| Width | 800-1200 px |
| Format | PNG |
| Theme | Dark theme (app default) |
| Background | Use real content (web page, document) |

## Preparation

1. Run CrossTrans (`python main.py` or EXE)
2. Make sure a working API key is configured (Settings > API Key > Test > success)
3. Enable dark theme (default)
4. Close unnecessary windows for a clean background

---

## 1. `quick_translate.png` — Quick Translate

**Description:** Popup showing translation near the cursor with all action buttons.

**Steps:**
1. Open a web page or document with English text
2. Select 1-2 English sentences
3. Press `Win+Alt+V` (translate to Vietnamese)
4. Wait for the popup to appear
5. **Capture the entire area:** highlighted source text + popup below

**Important:**
- All buttons must be visible: Copy, Replace, gear icon, Dictionary, Open Translator, x
- Popup should be close to the source text (not far away)
- Translation content should be meaningful (not an error)

---

## 2. Screenshot OCR — Two Images

### `screenshot_ocr_when_drag.png` — Drag Selection Overlay

**Description:** Semi-transparent overlay with drag selection area.

**Steps:**
1. Open a web page with English content (or an image with text)
2. Press `Win+Alt+S`
3. When the overlay appears, start dragging to select a region with text
4. **Capture while dragging** (overlay + red border selection)

**Important:**
- The overlay and selection area must be clearly visible
- The selected region should contain enough text for good OCR recognition

### `screenshot_ocr_result.png` — OCR Translation Result

**Description:** Translation popup showing the OCR result.

**Steps:**
1. Complete the drag selection from above
2. Wait for OCR processing and translation
3. **Capture the popup** showing the translated text

**Important:**
- The popup must show a meaningful translation result
- The source region should still be visible for context

---

## 3. `settings_api.png` — Settings > API Key

**Description:** API Key tab in Settings with a successful test result.

**Steps:**
1. Right-click the CT icon in system tray > Settings
2. Select the "API Key" tab
3. Make sure an API key is entered (hidden with * characters)
4. Click the "Test" button
5. Wait for the result showing "Text OK" (and "Image OK" if the model supports vision)
6. **Capture the entire Settings window**

**Important:**
- API key must be hidden (showing * instead of the actual key)
- Test result must show green (success)
- Provider and Model dropdowns must be visible

---

## 4. Replace Preview — Two Images

### `replace_preview_translated.png` — Translation Preview

**Description:** Popup showing translation with Replace button visible.

**Steps:**
1. Make sure Manual Replace mode is active (Settings > Hotkeys > Replace Mode: uncheck Quick Replace)
2. Open a text editor (Notepad, VS Code, etc.) and type an English sentence
3. Select the sentence
4. Press `Win+Alt+V` to translate
5. **Capture the popup** with the translation and Replace button visible

### `replace_preview_replaced.png` — After Replacement

**Description:** Preview showing strikethrough original text + translated text with Agree/Cancel buttons, or the "Replaced!" toast after clicking Agree.

**Steps:**
1. Click the "Replace" button in the popup
2. Preview appears: ~~original text~~ with translated text below, plus Agree and Cancel buttons
3. **Capture the entire area** showing the preview with Agree/Cancel buttons

**Important:**
- The original text with strikethrough must be clearly visible
- The translated text must be visible below
- Agree and Cancel buttons must be visible
- The background should show a text editor (for context)

---

## After Capturing

1. Place files in the `docs/screenshots/` folder:
   ```
   docs/screenshots/
   ├── quick_translate.png
   ├── screenshot_ocr_when_drag.png
   ├── screenshot_ocr_result.png
   ├── settings_api.png
   ├── replace_preview_translated.png
   └── replace_preview_replaced.png
   ```

2. Check file sizes (should be < 500 KB each, resize if needed)

3. Update README.md — replace placeholders with actual images:
   ```markdown
   ![Quick Translate](docs/screenshots/quick_translate.png)
   ```

4. Commit:
   ```bash
   git add docs/screenshots/ README.md
   git commit -m "Add screenshots to README"
   ```
