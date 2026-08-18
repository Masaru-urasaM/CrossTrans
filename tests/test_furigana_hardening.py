"""
Tests for the furigana hardening phase (F7).

Three things that all fail SILENTLY if they regress, which is why each gets a
test rather than a code review:

1. prewarm() - if it stops covering a provider, the cost simply moves back onto
   the UI thread. Nothing errors; the app just stutters on the first Japanese
   render.
2. The centralized FURIGANA_* constants - if a module re-declares one locally,
   the two copies drift and only one of them is the knob anybody edits.
3. The build guard - if it stops being invoked, an EXE without the reading
   dictionary builds and ships, and furigana is just quietly absent.

Pure logic and file inspection; no Tkinter, no API calls, no EXE is built.
"""
import importlib.util
import pathlib
import re
import threading

import pytest

from src import constants as C
from src.core import furigana as F
from src.ui import ruby_text as R

ROOT = pathlib.Path(__file__).resolve().parent.parent

FUGASHI_ONLY = pytest.mark.skipif(
    not F._FUGASHI.is_available(),
    reason="requires the Japanese NLP pack (fugashi + unidic)"
)


def _load_guard():
    """Import tools/verify_furigana_bundle.py, which is not on the import path."""
    path = ROOT / "tools" / "verify_furigana_bundle.py"
    spec = importlib.util.spec_from_file_location("verify_furigana_bundle", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


@pytest.fixture(autouse=True)
def _clear_cache():
    """Annotation is memoized, and prewarm() populates it; keep tests independent."""
    F.clear_cache()
    yield
    F.clear_cache()


# --------------------------------------------------------------------------- #
# prewarm()
# --------------------------------------------------------------------------- #
class TestPrewarm:
    def test_the_sample_would_actually_be_annotated(self):
        # A kanji-only sample passes should_annotate() only with a language hint,
        # and prewarm() passes none - so it would build nothing at all and the
        # regression would be invisible.
        assert F.should_annotate(C.FURIGANA_PREWARM_SAMPLE) is True

    def test_the_sample_produces_a_real_reading(self):
        # Proves the sample reaches the aligner, not just the tokenizer.
        segments = F.annotate(C.FURIGANA_PREWARM_SAMPLE)
        assert any(seg.ruby for seg in segments)

    def test_it_builds_the_fallback_provider_too(self, monkeypatch):
        # The regression this exists for: probing availability stops at the first
        # provider, but _refine_compounds() calls pykakasi on EVERY annotation, so
        # a probe leaves its ~215 ms construction on the first UI-thread render.
        # The preferred provider is faked in place - refinement is keyed on the
        # _FUGASHI identity, so a separate stub object would not reach kakasi at
        # all, and the test has to mean the same thing on a machine without the
        # Japanese NLP pack as on one with it.
        monkeypatch.setattr(F._FUGASHI, "_unavailable", False)
        monkeypatch.setattr(F._FUGASHI, "_tagger", object())
        monkeypatch.setattr(F._FUGASHI, "tokens", lambda text: [
            ("日本語", "ニホンゴ"), ("を", "ヲ"), ("読む", "ヨム")])
        monkeypatch.setattr(F._KAKASI, "_kks", None)
        monkeypatch.setattr(F._KAKASI, "_unavailable", False)

        F.prewarm()

        assert F._KAKASI._kks is not None

    @FUGASHI_ONLY
    def test_it_builds_both_real_providers(self, monkeypatch):
        monkeypatch.setattr(F._FUGASHI, "_tagger", None)
        monkeypatch.setattr(F._FUGASHI, "_unavailable", False)
        monkeypatch.setattr(F._KAKASI, "_kks", None)
        monkeypatch.setattr(F._KAKASI, "_unavailable", False)

        F.prewarm()

        assert F._FUGASHI._tagger is not None
        assert F._KAKASI._kks is not None

    def test_it_never_raises_when_a_provider_is_broken(self, monkeypatch):
        # Startup path: an exception here would kill the background thread and,
        # with it, the NLP prewarm that runs after it. prewarm() carries no
        # handler of its own - it inherits annotate()'s no-raise contract, so
        # this test guards that contract rather than a local try/except.
        class Exploding:
            name = "boom"

            def is_available(self):
                raise RuntimeError("dictionary corrupt")

            def tokens(self, text):
                raise RuntimeError("dictionary corrupt")

        monkeypatch.setattr(F, "_PROVIDERS", [Exploding()])
        F.prewarm()

    def test_it_is_safe_to_call_twice(self):
        F.prewarm()
        F.prewarm()


class TestStartupWiring:
    """prewarm() existed before this phase and was never called by anything."""

    def setup_method(self):
        self.source = (ROOT / "src" / "app.py").read_text(encoding="utf-8")

    def test_the_app_prewarms_the_engine(self):
        assert "furigana.prewarm()" in self.source

    def test_it_runs_on_the_background_thread(self):
        # On the UI thread this would be a ~215 ms freeze during startup, which
        # is precisely what the call is there to avoid.
        start = self.source.index("def prewarm_background")
        end = self.source.index("prewarm_thread = threading.Thread")
        assert start < self.source.index("furigana.prewarm()") < end
        assert "target=prewarm_background" in self.source
        assert "daemon=True" in self.source[end:end + 200]

    def test_it_is_skipped_when_furigana_is_off(self):
        start = self.source.index("def prewarm_background")
        block = self.source[start:self.source.index("furigana.prewarm()")]
        assert "self._ruby_enabled()" in block


# --------------------------------------------------------------------------- #
# Concurrency - prewarm now runs on a background thread
# --------------------------------------------------------------------------- #
class TestConcurrentAnnotation:
    def test_threads_annotating_at_once_agree_with_a_single_thread(self):
        # annotate() is reached from the UI thread at render time, from the
        # translation worker via generate_furigana(), and now from the startup
        # prewarm thread. A MeCab tagger is not documented thread-safe, so the
        # providers serialize; this is the test that says so.
        samples = ["今日は雨が降る", "日本語を読む", "毎日図書館へ行きます",
                   "会いたい人", "取り消しました"]
        expected = {text: F.annotate(text, "Japanese") for text in samples}
        F.clear_cache()

        results = {}
        errors = []

        def worker(text):
            try:
                for _ in range(10):
                    F.clear_cache()
                    results[text] = F.annotate(text, "Japanese")
            except Exception as e:  # pragma: no cover - only on a real race
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in samples]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert not errors
        assert results == expected


# --------------------------------------------------------------------------- #
# Centralized constants
# --------------------------------------------------------------------------- #
class TestConstantsAreCentralized:
    def test_the_engine_cap_comes_from_constants(self):
        assert F.MAX_RUBY_PAIRS == C.FURIGANA_MAX_RUBY_PAIRS

    def test_the_renderer_values_come_from_constants(self):
        assert R.MAX_ANNOTATE_CHARS == C.FURIGANA_MAX_ANNOTATE_CHARS
        assert R.CJK_FONT_FAMILY == C.FURIGANA_FONT_FAMILY
        assert R.BASE_FONT_SIZE == C.FURIGANA_BASE_FONT_SIZE
        assert R.RUBY_FONT_SIZE == C.FURIGANA_RUBY_FONT_SIZE
        assert R.DEFAULT_BG == C.FURIGANA_DEFAULT_BG
        assert R.BASE_FG == C.FURIGANA_BASE_FG
        assert R.KANJI_FG == C.FURIGANA_KANJI_FG
        assert R.RUBY_FG == C.FURIGANA_RUBY_FG
        assert R.RUBY_BG == C.FURIGANA_RUBY_BG
        assert R.LINE_SPACING == C.FURIGANA_LINE_SPACING
        assert R.RUBY_PAD_X == C.FURIGANA_RUBY_PAD_X
        assert R.RUBY_PAD_Y == C.FURIGANA_RUBY_PAD_Y
        assert R.WHEEL_UNITS == C.FURIGANA_WHEEL_UNITS
        assert R.DEFAULT_MAX_ROWS == C.FURIGANA_DEFAULT_MAX_ROWS

    def test_the_reading_pane_values_come_from_constants(self):
        # Imported here: importing src.app at module scope pulls in the whole UI.
        from src import app

        assert app.READING_PANE_DEBOUNCE_MS == C.FURIGANA_READING_PANE_DEBOUNCE_MS
        assert app.READING_PANE_MAX_ROWS == C.FURIGANA_READING_PANE_MAX_ROWS

    @pytest.mark.parametrize("relative, names", [
        ("src/ui/ruby_text.py", ["CJK_FONT_FAMILY", "BASE_FONT_SIZE",
                                 "RUBY_FONT_SIZE", "DEFAULT_BG", "BASE_FG",
                                 "KANJI_FG", "RUBY_FG", "RUBY_BG", "LINE_SPACING",
                                 "RUBY_PAD_X", "RUBY_PAD_Y", "WHEEL_UNITS",
                                 "DEFAULT_MAX_ROWS", "MAX_ANNOTATE_CHARS"]),
        ("src/core/furigana.py", ["MAX_RUBY_PAIRS"]),
    ])
    def test_no_module_redeclares_a_centralized_value(self, relative, names):
        # Equality above would still hold if someone pasted the literal back in
        # and it happened to match; this is what catches the paste itself, which
        # is how a "single knob" quietly becomes two.
        source = (ROOT / relative).read_text(encoding="utf-8")
        for name in names:
            assert not re.search(rf"^{name}\s*=", source, re.M), \
                f"{relative} re-declares {name} instead of importing it"


# --------------------------------------------------------------------------- #
# Build guard
# --------------------------------------------------------------------------- #
class TestBuildGuardChecks:
    def test_the_environment_can_supply_the_reading_dictionary(self):
        ok, message = guard.check_source()
        assert ok, message

    def test_the_bundled_path_matches_what_pyinstaller_collects(self):
        # If pykakasi moves its data directory the guard would look for a path
        # that can never exist and would fail every build.
        sources = guard.source_data_files()
        assert any(s.replace("\\", "/").endswith(guard.BUNDLED_PATH)
                   for s in sources), sources

    def test_the_other_pykakasi_data_files_do_not_satisfy_it(self, monkeypatch):
        # pykakasi ships nine more .db files, but they map kana between
        # romanization systems - none of them can turn a kanji into a reading.
        # A check loose enough to accept one would pass a build that has no
        # furigana in it at all.
        others = [s for s in guard.source_data_files()
                  if not s.replace("\\", "/").endswith(guard.DATA_FILE)]
        assert others, "expected pykakasi to ship more than the reading dictionary"
        monkeypatch.setattr(guard, "source_data_files", lambda: others)

        ok, message = guard.check_source()

        assert ok is False
        assert guard.DATA_FILE in message

    def test_the_other_bundled_data_files_do_not_satisfy_it(self, monkeypatch):
        monkeypatch.setattr(guard, "archive_names", lambda path: [
            "pykakasi/data/hepburndict3.db", "pykakasi/data/itaijidict4.db",
            "kanwadict4.db.txt", "pykakasi/py.typed"])

        ok, message = guard.check_exe(str(ROOT / "main.py"))

        assert ok is False
        assert "MISSING" in message

    def test_a_missing_file_is_reported_not_raised(self):
        ok, message = guard.check_exe(str(ROOT / "no-such-build.exe"))
        assert ok is False
        assert "no such file" in message

    def test_a_file_that_is_not_an_archive_is_reported_not_raised(self):
        # The build script runs this unattended; a traceback would abort the
        # script mid-way instead of printing the warning it exists to print.
        ok, message = guard.check_exe(str(ROOT / "main.py"))
        assert ok is False
        assert "archive" in message

    def test_exit_codes(self):
        assert guard.main(["--source"]) == 0
        assert guard.main(["--exe", str(ROOT / "no-such-build.exe")]) == 1

    def test_it_refuses_to_pass_when_asked_to_check_nothing(self):
        with pytest.raises(SystemExit):
            guard.main([])

    def test_a_real_build_carries_the_dictionary(self):
        builds = sorted((ROOT / "dist").glob("CrossTrans*.exe")) if (ROOT / "dist").is_dir() else []
        if not builds:
            pytest.skip("no built EXE in dist/ to inspect")
        ok, message = guard.check_exe(str(builds[-1]))
        assert ok, message


class TestBuildScriptInvokesTheGuard:
    """The check is worthless if build_exe.bat stops calling it."""

    def setup_method(self):
        self.script = (ROOT / "build_exe.bat").read_text(encoding="utf-8")

    def test_it_checks_the_environment_before_building(self):
        preflight = self.script.index("verify_furigana_bundle.py --source")
        build = self.script.index("python -m PyInstaller")
        assert preflight < build

    def test_a_failed_preflight_aborts_the_build(self):
        after = self.script[self.script.index("verify_furigana_bundle.py --source"):]
        block = after[:after.index("python -m PyInstaller")]
        assert "if errorlevel 1" in block
        assert "exit /b 1" in block

    def test_it_checks_the_built_exe(self):
        assert "verify_furigana_bundle.py --exe" in self.script
        assert "call :furigana_missing" in self.script
        assert ":furigana_missing" in self.script

    def test_no_comment_line_directly_precedes_a_block_close(self):
        # cmd.exe cannot parse a ':: comment' as the last statement inside a
        # parenthesised block - it dies with ") was unexpected at this time"
        # and the build never runs. Measured while writing this phase.
        lines = [line.strip() for line in self.script.splitlines()]
        for previous, current in zip(lines, lines[1:]):
            if current.startswith(")"):
                assert not previous.startswith("::"), \
                    f"'{previous}' directly precedes '{current}'"
