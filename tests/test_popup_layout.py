"""
Tests for src/ui/popup_layout.py - how big the quick-translate popup is and where it
goes, as numbers in and numbers out (Decision 34, TODO.md §5). No Tk.
"""
import pytest

from src.ui import popup_layout as L

WORK = L.WorkArea(0, 0, 1920, 1040)        # 1080p with a 40 px taskbar


def per_char(px):
    """A measure in which every character is `px` wide."""
    return lambda text: len(text) * px


class TestReadingWidth:
    def test_latin_text_reads_at_seventy_characters(self):
        assert L.reading_width("a" * 500, per_char(8)) == 70 * 8

    def test_cjk_text_at_thirty_six(self):
        assert L.reading_width("漢" * 300, per_char(15)) == 36 * 15

    def test_a_mix_in_proportion(self):
        assert L.reading_chars("ab漢字") == pytest.approx(70 + (36 - 70) * 0.5)

    def test_spaces_do_not_count_toward_the_share(self):
        assert L.cjk_share("漢 字\n") == 1.0

    def test_no_text_has_no_reading_width(self):
        assert L.reading_width("", per_char(8)) == 0
        assert L.reading_width("  \n ", per_char(8)) == 0

    @pytest.mark.parametrize('code_point', [0x304B, 0x30AB, 0x6F22, 0xD55C, 0xFF21, 0x3002])
    def test_kana_kanji_hangul_and_fullwidth_count_as_cjk(self, code_point):
        assert L.is_cjk(chr(code_point))

    @pytest.mark.parametrize('character', ["a", "é", "1", "-", " "])
    def test_latin_letters_digits_and_punctuation_do_not(self, character):
        assert not L.is_cjk(character)

    def test_the_widest_line_is_the_natural_width(self):
        assert L.natural_width("ab\nabcd\nabc", per_char(10)) == 40


class TestPopupWidth:
    def test_a_short_text_gets_the_rows_minimum(self):
        assert L.popup_width(natural=60, readable=530, insets=40, minimum=380,
                             work_width=1920) == 380

    def test_a_text_wider_than_the_minimum_is_hugged(self):
        assert L.popup_width(natural=450, readable=530, insets=40, minimum=380,
                             work_width=1920) == 490

    def test_a_long_text_wraps_at_the_reading_width(self):
        assert L.popup_width(natural=5000, readable=530, insets=40, minimum=380,
                             work_width=1920) == 570

    def test_the_rows_that_must_fit_win_over_reading(self):
        assert L.popup_width(natural=5000, readable=200, insets=40, minimum=735,
                             work_width=1920) == 735

    def test_never_wider_than_the_screen_allows(self):
        assert L.popup_width(natural=5000, readable=3000, insets=40, minimum=380,
                             work_width=1000) == 900

    def test_but_never_narrower_than_the_rows(self):
        assert L.popup_width(natural=5000, readable=3000, insets=40, minimum=950,
                             work_width=1000) == 950


class TestElide:
    def test_what_fits_is_untouched(self):
        assert L.elide("abc", len, 3) == "abc"

    def test_a_long_credit_is_cut_with_an_ellipsis(self):
        cut = L.elide("Translated with a-very-long-model-name (Provider)", len, 20)
        assert cut.endswith(L.ELLIPSIS) and len(cut) <= 20

    def test_with_no_room_only_the_ellipsis_is_left(self):
        assert L.elide("abc", len, 0) == L.ELLIPSIS


class TestHeightCap:
    def test_sixty_percent_of_the_work_area(self):
        assert L.height_cap(WORK) == 624

    def test_the_height_the_user_dragged_it_to_wins(self):
        assert L.height_cap(WORK, saved=800) == 800

    def test_but_it_stays_inside_the_work_area(self):
        assert L.height_cap(WORK, saved=5000) == 1020


class TestAllocate:
    def test_when_both_fit_both_get_what_they_need(self):
        assert L.allocate(500, 120, 80, min_translation=60, min_original=60) == \
            L.Heights(120, 80, False, False)

    def test_the_translation_comes_first(self):
        heights = L.allocate(500, 600, 600, min_translation=60, min_original=126)
        assert (heights.translation, heights.original) == (300, 200)
        assert heights.translation_capped and heights.original_capped

    def test_what_the_translation_leaves_goes_to_the_original(self):
        heights = L.allocate(500, 100, 900, min_translation=60, min_original=126)
        assert heights == L.Heights(100, 400, False, True)

    def test_a_collapsed_original_keeps_its_rows(self):
        heights = L.allocate(500, 100, 900, min_translation=60, min_original=126,
                             original_limit=126)
        assert heights == L.Heights(100, 126, False, True)

    def test_an_opened_original_takes_all_but_the_translations_first_rows(self):
        heights = L.allocate(500, 600, 900, min_translation=60, min_original=126,
                             original_share=1.0)
        assert (heights.translation, heights.original) == (60, 440)

    def test_the_share_never_eats_the_translations_first_rows(self):
        heights = L.allocate(200, 600, 900, min_translation=60, min_original=40,
                             original_share=1.0)
        assert heights.translation == 60 and heights.translation + heights.original == 200

    def test_without_an_original_the_translation_takes_the_room(self):
        assert L.allocate(300, 900, min_translation=60) == L.Heights(300, 0, True, False)

    def test_on_a_tiny_screen_the_minimums_win(self):
        heights = L.allocate(50, 600, 600, min_translation=60, min_original=40)
        assert (heights.translation, heights.original) == (60, 40)

    def test_any_capped(self):
        assert L.Heights(1, 1, False, True).any_capped
        assert not L.Heights(1, 1, False, False).any_capped


class TestPlace:
    ANCHOR = (900, 300)

    def test_below_right_when_it_fits(self):
        assert L.place(self.ANCHOR, 500, 300, WORK, min_height=100) == (915, 320, 300)

    def test_left_of_the_cursor_at_the_right_edge(self):
        x, _, _ = L.place((1800, 300), 500, 300, WORK, min_height=100)
        assert x == 1800 - 15 - 500

    def test_above_the_cursor_near_the_bottom(self):
        assert L.place((900, 900), 500, 300, WORK, min_height=100) == (915, 580, 300)

    def test_too_tall_for_either_side_takes_the_roomier_one_and_scrolls(self):
        below, above = L.room_beside(300, WORK)
        assert below > above
        assert L.place((900, 300), 500, 1000, WORK, min_height=100) == (915, 320, below)

    @pytest.mark.parametrize('anchor_y', [50, 300, 520, 700, 1000])
    @pytest.mark.parametrize('height', [100, 400, 900])
    def test_it_never_covers_the_cursor_while_a_side_has_room(self, anchor_y, height):
        x, y, h = L.place((900, anchor_y), 500, height, WORK, min_height=80)
        assert not L.covers(x, y, 500, h, (900, anchor_y))
        assert WORK.top < y and y + h < WORK.bottom

    def test_pinned_inside_when_no_side_holds_even_the_minimum(self):
        small = L.WorkArea(0, 0, 800, 200)
        x, y, h = L.place((400, 100), 300, 150, small, min_height=150)
        assert small.top + 10 <= y and y + h <= small.bottom - 10

    def test_a_monitor_left_of_the_primary_one(self):
        left = L.WorkArea(-1920, 0, 0, 1040)
        x, y, h = L.place((-100, 300), 500, 300, left, min_height=100)
        assert -1920 + 10 <= x and x + 500 <= -10

    def test_it_stays_inside_at_the_left_edge(self):
        x, _, _ = L.place((5, 300), 500, 300, WORK, min_height=100)
        assert x >= WORK.left + 10
