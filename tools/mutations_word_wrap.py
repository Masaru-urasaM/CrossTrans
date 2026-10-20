"""The Original-pane regression must catch character wrapping being restored."""
MUTATIONS = [
    ('original-splits-words-again', 'src/ui/quick_translate.py',
     "parent, expand=False, wrap=tk.WORD, bg='#2b2b2b')",
     "parent, expand=False, wrap=tk.CHAR, bg='#2b2b2b')",
     ['tests/test_popup_word_wrap.py', '-k', 'preserves_source_words']),
]
