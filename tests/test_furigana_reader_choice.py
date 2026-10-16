"""
Tests for D19's resolution (K14): UniDic is a download in Settings -> Dictionary,
not bundled.

pykakasi - the one reader every install has - reads a word differently from
fugashi + UniDic in 30% of real sentences (K1), and UniDic is ~250 MB, so the user
chose to offer it as the Japanese language pack. Installing or removing the pack
must change the reader furigana uses at once: a provider that failed to load is
otherwise never tried again before a restart, and the annotation cache keeps the
old readings. The Dictionary tab says which reader is in use.
"""
import importlib
import inspect
import sys
import tkinter as tk
import types

import pytest

from src.core import furigana as F
from src.ui.settings import dictionary_tab as D


@pytest.fixture
def provider_state():
    """Put the fugashi provider back as it was: a fake tagger must not outlive its test."""
    saved = (F._FUGASHI._tagger, F._FUGASHI._unavailable)
    yield
    F._FUGASHI._tagger, F._FUGASHI._unavailable = saved
    F.clear_cache()


class FakeTagger:
    def __call__(self, text):
        return []


def fake_fugashi(tagger):
    return types.SimpleNamespace(Tagger=tagger)


class TestRefreshProviders:
    def test_a_pack_installed_after_a_failed_load_is_found(self, monkeypatch, provider_state):
        # A session that started without the pack: fugashi failed to load once.
        F._FUGASHI._tagger, F._FUGASHI._unavailable = None, True
        monkeypatch.setitem(sys.modules, 'fugashi', fake_fugashi(FakeTagger))
        assert F.active_provider_name() == 'pykakasi'      # never looked for again by itself
        assert F.refresh_providers() == 'fugashi'
        assert F.active_provider_name() == 'fugashi'

    def test_a_reader_that_cannot_load_leaves_pykakasi(self, monkeypatch, provider_state):
        def cannot_load():
            raise OSError("libmecab.dll could not be loaded")
        monkeypatch.setitem(sys.modules, 'fugashi', fake_fugashi(cannot_load))
        assert F.refresh_providers() == 'pykakasi'

    def test_the_old_readings_are_dropped(self, provider_state):
        F.annotate('日本語を勉強します')
        assert F._annotate_cached.cache_info().currsize > 0
        F.refresh_providers()
        assert F._annotate_cached.cache_info().currsize == 0

    def test_a_package_installed_since_start_up_can_be_imported(self, monkeypatch,
                                                                 provider_state):
        # The import system caches directory listings: without this, a package
        # pip put on sys.path after start-up is not found.
        calls = []
        monkeypatch.setattr(importlib, 'invalidate_caches', lambda: calls.append(1))
        F.refresh_providers()
        assert calls == [1]


class TestApplyToFurigana:
    def test_the_japanese_pack_installed_or_removed(self, monkeypatch):
        calls = []
        monkeypatch.setattr(F, 'refresh_providers', lambda: calls.append(1))
        D._apply_to_furigana('Japanese', True)
        assert calls == [1]

    @pytest.mark.parametrize('language, success', [
        ('Japanese', False), ('Chinese (Simplified)', True), ('Korean', True)])
    def test_anything_else_leaves_furigana_alone(self, monkeypatch, language, success):
        calls = []
        monkeypatch.setattr(F, 'refresh_providers', lambda: calls.append(1))
        D._apply_to_furigana(language, success)
        assert calls == []

    @pytest.mark.parametrize('verb', ['install', 'uninstall'])
    def test_every_install_and_uninstall_applies_it(self, verb):
        # Single and bulk, both directions: four call sites, each followed by it.
        source = inspect.getsource(D)
        call = f'success, error = nlp_manager.{verb}(language, progress_callback)'
        assert source.count(call) == 2
        assert source.count(call + '\n            _apply_to_furigana(language, success)') == 2


class TestReaderNote:
    def test_accurate(self):
        assert 'accurate readings (UniDic' in D.furigana_reader_note(True, True)

    def test_installed_but_not_loadable(self):
        note = D.furigana_reader_note(False, True)
        assert 'basic readings' in note and 'could not be loaded' in note

    def test_not_installed_says_how_and_what_it_costs(self):
        note = D.furigana_reader_note(False, False)
        assert 'Install the Japanese pack' in note and '250 MB' in note
        assert 'no restart' in note

    @pytest.mark.parametrize('provider, installed, accurate', [
        ('fugashi', True, True), ('pykakasi', True, False), ('pykakasi', False, False)])
    def test_the_tab_shows_the_reader_in_use(self, tk_root, monkeypatch,
                                            provider, installed, accurate):
        from src.core.nlp_manager import nlp_manager
        monkeypatch.setattr(F, 'active_provider_name', lambda: provider)
        monkeypatch.setattr(nlp_manager, 'is_installed', lambda language: installed)
        frame = tk.Frame(tk_root)
        try:
            tab = D.DictionaryTabMixin()
            tab._create_furigana_reader_note(frame)
            assert (tab.furigana_reader_label.cget('text')
                    == D.furigana_reader_note(accurate, installed))
        finally:
            frame.destroy()

    def test_the_pack_is_fugashi_and_unidic_at_its_measured_size(self):
        from src.core.nlp_manager import LANGUAGE_PACKS
        pack = LANGUAGE_PACKS['Japanese']
        assert pack.packages == ['fugashi', 'unidic-lite']
        assert pack.size_mb == 250
