"""
History Manager for CrossTrans.
Handles saving, retrieving, and managing translation history.
"""
import time
import uuid
from typing import List, Dict, Any


class HistoryManager:
    """Manages translation history with a limit on entries."""
    
    MAX_HISTORY = 100

    def __init__(self, config):
        self.config = config

    def add_entry(self, original: str, translated: str, target_lang: str,
                  source_type: str = "text", model_used: str = "Auto",
                  source_lang: str = ""):
        """Add a new translation entry to history."""
        if not self.config.get('history_enabled', True):
            return

        # Don't save if original text is empty or too short/trivial
        if not original or len(original.strip()) < 2:
            return

        # Auto-detect source language if not provided
        if not source_lang:
            source_lang = self._detect_language(original)

        entry = {
            'id': str(uuid.uuid4()),
            'timestamp': time.time(),
            'original': original,
            'translated': translated,
            'target_lang': target_lang,
            'source_lang': source_lang,
            'source_type': source_type,
            'model_used': model_used
        }

        history = self.config.get('history', [])
        history.insert(0, entry)
        
        # Enforce limit
        if len(history) > self.MAX_HISTORY:
            history = history[:self.MAX_HISTORY]
            
        self.config.set('history', history)

    def get_history(self) -> List[Dict[str, Any]]:
        """Get full history list."""
        return self.config.get('history', [])

    def clear_history(self):
        """Clear all history."""
        self.config.set('history', [])

    def delete_entry(self, entry_id: str):
        """Delete a specific entry by ID."""
        history = self.config.get('history', [])
        history = [h for h in history if h.get('id') != entry_id]
        self.config.set('history', history)

    def _detect_language(self, text: str) -> str:
        """Simple language detection based on character ranges."""
        if not text:
            return "Unknown"

        # Count characters in different ranges
        cjk = 0  # Chinese/Japanese/Korean
        hiragana = 0
        katakana = 0
        korean = 0
        vietnamese = 0
        latin = 0
        cyrillic = 0

        vietnamese_chars = set('àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ')

        for char in text.lower():
            code = ord(char)
            if 0x4E00 <= code <= 0x9FFF:  # CJK
                cjk += 1
            elif 0x3040 <= code <= 0x309F:  # Hiragana
                hiragana += 1
            elif 0x30A0 <= code <= 0x30FF:  # Katakana
                katakana += 1
            elif 0xAC00 <= code <= 0xD7AF:  # Korean
                korean += 1
            elif char in vietnamese_chars:
                vietnamese += 1
            elif 0x0400 <= code <= 0x04FF:  # Cyrillic
                cyrillic += 1
            elif char.isalpha():
                latin += 1

        # Determine language
        total = cjk + hiragana + katakana + korean + vietnamese + latin + cyrillic
        if total == 0:
            return "Unknown"

        if hiragana + katakana > 0:
            return "Japanese"
        if korean > total * 0.3:
            return "Korean"
        if cjk > total * 0.3:
            return "Chinese"
        if vietnamese > 0:
            return "Vietnamese"
        if cyrillic > total * 0.3:
            return "Russian"
        if latin > 0:
            return "English"  # Default for Latin scripts

        return "Unknown"