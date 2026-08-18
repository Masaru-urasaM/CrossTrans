"""
Tests for furigana on the dictionary word chips and custom-box tags (F6).

These chips are not text in a widget - they are embedded `tk.Label`s and
`tk.Frame`s with their own click, hover, selection and right-click-drag
behaviour, so the risk is not the readings themselves but everything that has to
keep working around them: baseline alignment against the plain chips, selection
recolouring the reading too, the box growing so a reading is not clipped, the
drag ghost previewing the same structure, and `get_content()` still joining the
words the way it did.

Skipped automatically when no display is available (see the `tk_root` fixture).
"""
import tkinter as tk

import pytest

from src.core import furigana as F
from src.core.furigana import RubySegment
from src.ui.custom_word_boxes import (RUBY_FG as TAG_RUBY_FG, TAG_BG,
                                      CustomWordBoxesFrame, WordTag, _ruby_rows)
from src.ui.dictionary_mode import (RUBY_SELECTED_FG, WORD_BG, WORD_SELECTED_BG,
                                    WordButtonFrame, WordLabel)
from src.ui.ruby_text import RUBY_FG, RubyRow

HAS_PROVIDER = pytest.mark.skipif(
    not F.is_available(),
    reason="requires a reading provider (fugashi or pykakasi)"
)

JP_SENTENCE = "今日は日本語を勉強します。"
JP_MULTI = "取り消し"          # two readings in one token: 取[と]り消[け]し
EN_SENTENCE = "I study Japanese every day."

SEGMENTS = (RubySegment("取", "と"), RubySegment("り", None),
            RubySegment("消", "け"), RubySegment("し", None))
PLAIN_SEGMENTS = (RubySegment("word", None),)


@pytest.fixture(autouse=True)
def _clear_cache():
    F.clear_cache()
    yield
    F.clear_cache()


@pytest.fixture
def mapped_root(tk_root):
    """A briefly visible root: winfo_height() is 1 while it stays withdrawn, and
    the drag handlers work in screen coordinates."""
    tk_root.geometry("700x500+80+80")
    tk_root.deiconify()
    tk_root.update()
    yield tk_root
    tk_root.withdraw()
    tk_root.update_idletasks()


@pytest.fixture
def text_widget(tk_root):
    box = tk.Text(tk_root, height=4, width=40)
    box.pack()
    tk_root.update_idletasks()
    yield box
    box.destroy()


@pytest.fixture
def make_frame(tk_root):
    """Factory for a real WordButtonFrame, destroyed on teardown."""
    created = []

    def _make(text=JP_SENTENCE, language="Japanese", furigana_enabled=True):
        frame = WordButtonFrame(tk_root, text, on_selection_change=lambda t: None,
                                language=language,
                                furigana_enabled=furigana_enabled)
        frame.pack(fill=tk.BOTH, expand=True)
        tk_root.update_idletasks()
        created.append(frame)
        return frame

    yield _make
    for frame in created:
        try:
            frame.destroy()
        except tk.TclError:
            pass


@pytest.fixture
def make_boxes(tk_root):
    created = []

    def _make(language="Japanese", furigana_enabled=True):
        boxes = CustomWordBoxesFrame(tk_root, language=language,
                                     furigana_enabled=furigana_enabled)
        boxes.pack(fill=tk.X)
        tk_root.update_idletasks()
        created.append(boxes)
        return boxes

    yield _make
    for boxes in created:
        try:
            boxes.destroy()
        except tk.TclError:
            pass


def chip(frame, word):
    for label in frame.word_labels:
        if label.word == word:
            return label
    raise AssertionError(f"no chip for {word!r}: "
                         f"{[w.word for w in frame.word_labels]}")


# --------------------------------------------------------------------------- #
# WordLabel
# --------------------------------------------------------------------------- #
class TestWordLabel:
    def test_plain_word_keeps_the_single_label_chip(self, text_widget):
        # Non-Japanese dictionary mode must be exactly what it was.
        label = WordLabel(text_widget, "word", 0, lambda *a: None, lambda *a: None,
                          segments=PLAIN_SEGMENTS)
        assert isinstance(label.widget, tk.Label)
        assert label.has_ruby is False
        assert label.label is label.widget

    def test_no_segments_at_all_is_also_plain(self, text_widget):
        label = WordLabel(text_widget, "word", 0, lambda *a: None, lambda *a: None)
        assert isinstance(label.widget, tk.Label)
        assert label.has_ruby is False

    def test_annotated_word_becomes_a_two_row_chip(self, text_widget):
        label = WordLabel(text_widget, JP_MULTI, 0, lambda *a: None,
                          lambda *a: None, segments=SEGMENTS)
        assert isinstance(label.row, RubyRow)
        assert label.has_ruby is True
        assert [r.cget('text') for r in label.row.readings] == ['と', '', 'け', '']
        assert [b.cget('text') for b in label.row.bases] == ['取', 'り', '消', 'し']

    def test_bases_share_one_row(self, text_widget, tk_root):
        # A single label per reading would break the word into stacked pieces.
        label = WordLabel(text_widget, JP_MULTI, 0, lambda *a: None,
                          lambda *a: None, segments=SEGMENTS)
        text_widget.window_create('1.0', window=label.widget, align='baseline')
        tk_root.update_idletasks()
        rows = {b.winfo_rooty() for b in label.row.bases}
        assert len(rows) == 1, f"bases on {len(rows)} different rows"

    def test_selection_recolours_the_reading_too(self, text_widget):
        label = WordLabel(text_widget, JP_MULTI, 0, lambda *a: None,
                          lambda *a: None, segments=SEGMENTS)
        label.set_selected(True)
        assert {w.cget('bg') for w in label.row.widgets} == {WORD_SELECTED_BG}
        # RUBY_FG on the orange highlight would be unreadable.
        assert {r.cget('fg') for r in label.row.readings} == {RUBY_SELECTED_FG}
        label.set_selected(False)
        assert {w.cget('bg') for w in label.row.widgets} == {WORD_BG}
        assert {r.cget('fg') for r in label.row.readings} == {RUBY_FG}

    def test_selection_still_works_on_a_plain_chip(self, text_widget):
        label = WordLabel(text_widget, "word", 0, lambda *a: None, lambda *a: None)
        label.set_selected(True)
        assert label.widget.cget('bg') == WORD_SELECTED_BG
        label.set_selected(False)
        assert label.widget.cget('bg') == WORD_BG

    def test_hover_underlines_every_base(self, text_widget):
        label = WordLabel(text_widget, JP_MULTI, 0, lambda *a: None,
                          lambda *a: None, segments=SEGMENTS)
        label._handle_enter(type('E', (), {'state': 0})())
        assert all('underline' in str(b.cget('font')) for b in label.row.bases)
        label._handle_leave(None)
        assert not any('underline' in str(b.cget('font')) for b in label.row.bases)

    def test_click_reaches_the_callback_from_any_part(self, text_widget):
        clicks = []
        label = WordLabel(text_widget, JP_MULTI, 7,
                          on_click=lambda i, e: clicks.append(i),
                          on_drag_enter=lambda i: None, segments=SEGMENTS)
        # A click on the reading must count: it is inside the word's chip.
        for widget in label.row.widgets:
            assert widget.bind('<Button-1>'), "part is not clickable"
        label._handle_click(None)
        assert clicks == [7]

    def test_wheel_is_bound_on_every_part(self, text_widget):
        # An embedded widget swallows <MouseWheel>; chips cover most of the area.
        label = WordLabel(text_widget, JP_MULTI, 0, lambda *a: None,
                          lambda *a: None, segments=SEGMENTS,
                          on_wheel=lambda e: None)
        for widget in label.row.widgets:
            assert widget.bind('<MouseWheel>'), "wheel dead zone over a chip"

    def test_destroy_removes_the_whole_chip(self, text_widget):
        label = WordLabel(text_widget, JP_MULTI, 0, lambda *a: None,
                          lambda *a: None, segments=SEGMENTS)
        label.destroy()
        assert not label.widget.winfo_exists()


# --------------------------------------------------------------------------- #
# The word area
# --------------------------------------------------------------------------- #
class TestWordArea:
    @HAS_PROVIDER
    def test_japanese_chips_are_annotated(self, make_frame):
        frame = make_frame()
        assert chip(frame, "勉強").has_ruby is True
        assert chip(frame, "今日").has_ruby is True

    @HAS_PROVIDER
    def test_reading_uses_the_sentence_not_the_chip(self, make_frame):
        frame = make_frame()
        assert chip(frame, "今日").row.readings[0].cget('text') == "きょう"

    @HAS_PROVIDER
    def test_a_chip_that_splits_a_compound_stays_bare(self, make_frame):
        # 日本語 is tokenized as 日本 + 語 here; 日本 alone would read にっぽん.
        frame = make_frame()
        for word in ("日本", "語"):
            try:
                assert chip(frame, word).has_ruby is False
            except AssertionError as exc:
                if "no chip for" in str(exc):
                    pytest.skip("tokenizer kept the compound together")
                raise

    def test_latin_text_produces_only_plain_chips(self, make_frame):
        frame = make_frame(EN_SENTENCE, language="English")
        assert frame.word_labels
        assert all(not label.has_ruby for label in frame.word_labels)
        assert all(isinstance(label.widget, tk.Label)
                   for label in frame.word_labels)

    @HAS_PROVIDER
    def test_toggle_off_produces_only_plain_chips(self, make_frame):
        frame = make_frame(furigana_enabled=False)
        assert frame.word_labels
        assert all(not label.has_ruby for label in frame.word_labels)

    @HAS_PROVIDER
    def test_chips_are_baseline_aligned(self, make_frame):
        # Tk's default 'center' lifts the plain chips 7px off the annotated
        # chips' baseline (measured).
        frame = make_frame()
        dumped = frame.text_widget.dump('1.0', tk.END, window=True)
        assert dumped
        for _kind, name, index in dumped:
            assert frame.text_widget.window_cget(index, 'align') == 'baseline'

    @HAS_PROVIDER
    def test_the_frame_binds_its_wheel_handler_to_the_chips(self, make_frame):
        # Asserted on the real frame, not on a hand-built WordLabel: the wiring
        # is what breaks, not the binding loop.
        frame = make_frame()
        assert frame.text_widget.bind('<MouseWheel>')
        for label in frame.word_labels:
            assert label.widget.bind('<MouseWheel>'),                 f"wheel dead zone over {label.word!r}"

    @HAS_PROVIDER
    def test_selected_text_is_unaffected_by_readings(self, make_frame):
        frame = make_frame()
        target = chip(frame, "勉強")
        frame._toggle_word(target.index)
        assert frame.get_selected_text() == "勉強"
        assert frame.get_selected_words() == ["勉強"]

    def test_annotation_failure_falls_back_to_plain_chips(self, make_frame,
                                                         monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("provider exploded")

        monkeypatch.setattr('src.ui.dictionary_mode.furigana.annotate_tokens', boom)
        frame = make_frame()
        assert frame.word_labels
        assert all(not label.has_ruby for label in frame.word_labels)


# --------------------------------------------------------------------------- #
# Custom box tags
# --------------------------------------------------------------------------- #
class TestWordTag:
    def test_plain_tag_is_unchanged(self, text_widget):
        tag = WordTag(text_widget, "word", lambda t: None)
        assert tag.has_ruby is False
        assert tag.row is None
        assert tag.close_btn.cget('text') == '×'

    def test_annotated_tag_puts_the_close_button_on_the_word_row(self, text_widget):
        tag = WordTag(text_widget, JP_MULTI, lambda t: None, segments=SEGMENTS)
        assert tag.has_ruby is True
        info = tag.close_btn.grid_info()
        assert int(info['row']) == 1                 # the word row, not the reading
        assert int(info['column']) == len(SEGMENTS)

    def test_dimming_covers_the_reading(self, text_widget):
        tag = WordTag(text_widget, JP_MULTI, lambda t: None, segments=SEGMENTS)
        tag.set_dimmed(True)
        assert TAG_BG not in {w.cget('bg') for w in tag._parts}
        assert TAG_RUBY_FG not in {r.cget('fg') for r in tag.row.readings}
        tag.set_dimmed(False)
        assert {w.cget('bg') for w in tag._parts} == {TAG_BG}
        assert {r.cget('fg') for r in tag.row.readings} == {TAG_RUBY_FG}

    def test_dimming_a_plain_tag_still_works(self, text_widget):
        tag = WordTag(text_widget, "word", lambda t: None)
        tag.set_dimmed(True)
        assert tag.label.cget('bg') != TAG_BG
        tag.set_dimmed(False)
        assert tag.label.cget('bg') == TAG_BG

    def test_remove_button_fires(self, text_widget):
        removed = []
        tag = WordTag(text_widget, JP_MULTI, removed.append, segments=SEGMENTS)
        tag._remove()
        assert removed == [tag]


class TestCustomBoxes:
    @HAS_PROVIDER
    def test_tag_from_a_japanese_word_gets_readings(self, make_boxes):
        boxes = make_boxes()
        boxes.add_word_to_box(JP_MULTI)
        tag = boxes._boxes[0]._tags[-1]
        assert tag.has_ruby is True

    @HAS_PROVIDER
    def test_box_grows_so_the_reading_is_not_clipped(self, make_boxes, mapped_root):
        # `height` counts base-font rows; a tag with a reading is taller than one.
        boxes = make_boxes()
        box = boxes._boxes[0]
        assert int(box.text_widget.cget('height')) == 1
        boxes.add_word_to_box(JP_MULTI)
        mapped_root.update()
        assert int(box.text_widget.cget('height')) == _ruby_rows() > 1
        tag = box._tags[-1]
        assert box.text_widget.winfo_height() >= tag.frame.winfo_reqheight()

    @HAS_PROVIDER
    def test_box_shrinks_again_when_the_tag_goes(self, make_boxes, tk_root):
        boxes = make_boxes()
        box = boxes._boxes[0]
        boxes.add_word_to_box(JP_MULTI)
        tk_root.update_idletasks()
        box._remove_tag(box._tags[-1])
        tk_root.update_idletasks()
        assert int(box.text_widget.cget('height')) == 1

    def test_latin_tag_leaves_the_box_at_one_row(self, make_boxes):
        boxes = make_boxes(language="English")
        boxes.add_word_to_box("word")
        assert int(boxes._boxes[0].text_widget.cget('height')) == 1

    @HAS_PROVIDER
    def test_toggle_off_keeps_tags_plain(self, make_boxes):
        boxes = make_boxes(furigana_enabled=False)
        boxes.add_word_to_box(JP_MULTI)
        assert boxes._boxes[0]._tags[-1].has_ruby is False
        assert int(boxes._boxes[0].text_widget.cget('height')) == 1

    @HAS_PROVIDER
    def test_content_joining_is_unchanged(self, make_boxes):
        # CJK tags join without a space; readings must not leak into the phrase.
        boxes = make_boxes()
        box = boxes._boxes[0]
        boxes.add_word_to_box("無礼", box)
        boxes.add_word_to_box("講", box)
        assert box.get_content() == "無礼講"

    @HAS_PROVIDER
    def test_tags_are_baseline_aligned(self, make_boxes):
        boxes = make_boxes()
        box = boxes._boxes[0]
        boxes.add_word_to_box(JP_MULTI, box)
        dumped = box.text_widget.dump('1.0', tk.END, window=True)
        assert dumped
        for _kind, _name, index in dumped:
            assert box.text_widget.window_cget(index, 'align') == 'baseline'


# --------------------------------------------------------------------------- #
# Drag and drop
# --------------------------------------------------------------------------- #
class FakeEvent:
    def __init__(self, x_root=0, y_root=0):
        self.x_root = x_root
        self.y_root = y_root
        self.state = 0


def centre(widget):
    return (widget.winfo_rootx() + widget.winfo_width() // 2,
            widget.winfo_rooty() + widget.winfo_height() // 2)


def ghost_texts(ghost):
    found = []

    def walk(widget):
        for child in widget.winfo_children():
            if isinstance(child, tk.Label):
                found.append(child.cget('text'))
            walk(child)

    walk(ghost)
    return found


class TestDragAndDrop:
    @HAS_PROVIDER
    def test_ghost_previews_the_readings(self, make_frame, make_boxes, tk_root):
        # Never a concatenated reading string: 取り消し would preview as とけ.
        frame = make_frame(JP_MULTI + "をします。")
        boxes = make_boxes()
        frame.set_drop_target(boxes)
        target = chip(frame, JP_MULTI)
        frame._start_drag_to_box(target.word, FakeEvent(*centre(target.widget)))
        tk_root.update_idletasks()
        try:
            texts = ghost_texts(frame._drag_ghost)
            assert 'と' in texts and 'け' in texts
            assert '取' in texts and '消' in texts
            assert 'とけ' not in texts
        finally:
            frame._end_drag(FakeEvent(-1, -1))
        assert frame._drag_ghost is None

    def test_plain_ghost_is_a_single_label(self, make_frame, make_boxes, tk_root):
        frame = make_frame(EN_SENTENCE, language="English")
        boxes = make_boxes(language="English")
        frame.set_drop_target(boxes)
        target = chip(frame, "study")
        frame._start_drag_to_box(target.word, FakeEvent(*centre(target.widget)))
        tk_root.update_idletasks()
        try:
            assert ghost_texts(frame._drag_ghost) == ["study"]
        finally:
            frame._end_drag(FakeEvent(-1, -1))

    @HAS_PROVIDER
    def test_dropping_a_chip_creates_an_annotated_tag(self, make_frame,
                                                     make_boxes, mapped_root):
        frame = make_frame(JP_MULTI + "をします。")
        boxes = make_boxes()
        frame.set_drop_target(boxes)
        box = boxes._boxes[0]
        mapped_root.update()
        target = chip(frame, JP_MULTI)
        frame._start_drag_to_box(target.word, FakeEvent(*centre(target.widget)))
        frame._drag_motion(FakeEvent(*centre(box.text_widget)))
        frame._end_drag(FakeEvent(*centre(box.text_widget)))
        mapped_root.update()
        assert [t.word for t in box._tags] == [JP_MULTI]
        assert box._tags[0].has_ruby is True
        assert box.get_content() == JP_MULTI

    @HAS_PROVIDER
    def test_reordering_keeps_the_readings(self, make_boxes, mapped_root):
        boxes = make_boxes()
        box = boxes._boxes[0]
        boxes.add_word_to_box("勉強", box)
        boxes.add_word_to_box("会議", box)
        mapped_root.update()
        second = box._tags[-1]
        boxes._on_tag_drag_start(second, FakeEvent(*centre(second.frame)))
        left = FakeEvent(box.text_widget.winfo_rootx() + 2,
                         box.text_widget.winfo_rooty() + 2)
        boxes._on_tag_drag_motion(left)
        boxes._on_tag_drag_end(left)
        mapped_root.update()
        assert [t.word for t in box._tags] == ["会議", "勉強"]
        assert all(t.has_ruby for t in box._tags)
        assert box.get_content() == "会議勉強"

    @HAS_PROVIDER
    def test_a_cancelled_drag_restores_the_tag(self, make_boxes, tk_root):
        boxes = make_boxes()
        box = boxes._boxes[0]
        boxes.add_word_to_box("勉強", box)
        tk_root.update_idletasks()
        tag = box._tags[0]
        boxes._on_tag_drag_start(tag, FakeEvent(*centre(tag.frame)))
        boxes._on_tag_drag_end(FakeEvent(-1, -1))     # released outside, no move
        assert {w.cget('bg') for w in tag._parts} == {TAG_BG}
        assert {r.cget('fg') for r in tag.row.readings} == {TAG_RUBY_FG}
