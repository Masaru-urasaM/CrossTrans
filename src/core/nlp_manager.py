"""
NLP Language Pack Manager for CrossTrans.

Handles optional download and management of NLP libraries for smart
word tokenization in Dictionary mode.

Supports 30+ languages via:
- UDPipe for European languages (Python 3.14 compatible)
- Specialized libraries for Asian languages (Vietnamese, Japanese, Chinese, Korean, Thai)
"""
import gc
import subprocess
import sys
import importlib
import re
import logging
from typing import Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass, field


@dataclass
class LanguagePack:
    """Language pack configuration."""
    name: str
    code: str
    packages: List[str]  # pip packages to install
    post_install: Optional[str] = None  # command to run after install
    size_mb: int = 0
    module_check: str = ""  # module to import to check if installed
    spacy_model: str = ""  # spaCy model name if using spaCy
    udpipe_model: str = ""  # UDPipe model name if using UDPipe
    category: str = "Other"  # Category for grouping in UI


@dataclass
class ParsedToken:
    """Token with dependency and POS information from CoNLL-U format.

    Used for grouping compound words and phrasal verbs.
    """
    id: int          # Token index in sentence (1-based)
    form: str        # Word form/surface text
    head: int        # ID of head token (0 = root)
    deprel: str      # Dependency relation to head (e.g., "compound", "compound:prt")
    upos: str = ""   # Universal POS tag (NOUN, VERB, ADJ, CCONJ, etc.)


# Dependency relations that indicate multi-word expressions
# These tokens should be merged with their head token
COMPOUND_RELATIONS = {
    'compound',       # General compounds: "ice cream", "New York"
    'compound:prt',   # Phrasal verb particles: "give UP", "break DOWN"
    'flat',           # Flat structures (names): "John Smith"
    'flat:name',      # Named entities: "New York City"
    'flat:foreign',   # Foreign words kept together
    'fixed',          # Fixed multi-word expressions: "as well as"
    'goeswith',       # Parts of same word incorrectly split
}

# POS constraints for compound relations
# Defines which POS combinations are valid for each relation type
COMPOUND_POS_CONSTRAINTS = {
    'compound': {'NOUN', 'PROPN'},       # Both must be NOUN/PROPN (not ADJ, CCONJ, etc.)
    'compound:prt': {'VERB'},            # Head must be VERB (phrasal verbs)
    'flat': {'PROPN'},                   # Both must be PROPN (names only)
    'flat:name': {'PROPN'},              # Names only
    'flat:foreign': None,                # No constraint (foreign words)
    'fixed': None,                       # No constraint (fixed expressions)
    'goeswith': None,                    # No constraint (split words)
}


def get_udpipe_model_dir() -> str:
    """Get directory for UDPipe models."""
    import os
    return os.path.join(os.path.expanduser("~"), ".udpipe_models")


def get_udpipe_model_path(model_name: str) -> str:
    """Get full path to a UDPipe model file."""
    import os
    return os.path.join(get_udpipe_model_dir(), f"{model_name}.udpipe")


# UDPipe model download URLs from LINDAT repository
# https://lindat.mff.cuni.cz/repository/xmlui/handle/11234/1-3131
UDPIPE_MODEL_URLS = {
    "english-ewt-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/english-ewt-ud-2.5-191206.udpipe",
    "german-gsd-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/german-gsd-ud-2.5-191206.udpipe",
    "french-gsd-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/french-gsd-ud-2.5-191206.udpipe",
    "spanish-ancora-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/spanish-ancora-ud-2.5-191206.udpipe",
    "italian-isdt-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/italian-isdt-ud-2.5-191206.udpipe",
    "portuguese-bosque-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/portuguese-bosque-ud-2.5-191206.udpipe",
    "dutch-alpino-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/dutch-alpino-ud-2.5-191206.udpipe",
    "polish-pdb-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/polish-pdb-ud-2.5-191206.udpipe",
    "russian-syntagrus-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/russian-syntagrus-ud-2.5-191206.udpipe",
    "ukrainian-iu-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/ukrainian-iu-ud-2.5-191206.udpipe",
    "greek-gdt-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/greek-gdt-ud-2.5-191206.udpipe",
    "romanian-rrt-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/romanian-rrt-ud-2.5-191206.udpipe",
    "croatian-set-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/croatian-set-ud-2.5-191206.udpipe",
    "catalan-ancora-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/catalan-ancora-ud-2.5-191206.udpipe",
    "danish-ddt-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/danish-ddt-ud-2.5-191206.udpipe",
    "finnish-tdt-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/finnish-tdt-ud-2.5-191206.udpipe",
    "norwegian-bokmaal-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/norwegian-bokmaal-ud-2.5-191206.udpipe",
    "swedish-talbanken-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/swedish-talbanken-ud-2.5-191206.udpipe",
    "slovenian-ssj-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/slovenian-ssj-ud-2.5-191206.udpipe",
    "lithuanian-alksnis-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/lithuanian-alksnis-ud-2.5-191206.udpipe",
    "macedonian-mtb-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/macedonian-mtb-ud-2.5-191206.udpipe",
    "hebrew-htb-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/hebrew-htb-ud-2.5-191206.udpipe",
    "indonesian-gsd-ud-2.5": "https://lindat.mff.cuni.cz/repository/xmlui/bitstream/handle/11234/1-3131/indonesian-gsd-ud-2.5-191206.udpipe",
}


# Language packs organized by category
# Using UDPipe for European languages (Python 3.14 compatible, replaces spaCy)
# Specialized libraries for Asian languages where standard tokenization is inadequate

LANGUAGE_PACKS: Dict[str, LanguagePack] = {
    # === ASIAN LANGUAGES (Specialized libraries for better tokenization) ===
    "Vietnamese": LanguagePack(
        name="Vietnamese",
        code="vi",
        packages=["underthesea"],
        size_mb=45,
        module_check="underthesea",
        category="Asian"
    ),
    "Japanese": LanguagePack(
        name="Japanese",
        code="ja",
        packages=["fugashi", "unidic-lite"],
        size_mb=200,
        module_check="fugashi",
        category="Asian"
    ),
    "Chinese (Simplified)": LanguagePack(
        name="Chinese (Simplified)",
        code="zh",
        packages=["jieba"],
        size_mb=15,
        module_check="jieba",
        category="Asian"
    ),
    "Chinese (Traditional)": LanguagePack(
        name="Chinese (Traditional)",
        code="zh-tw",
        packages=["jieba"],
        size_mb=15,
        module_check="jieba",
        category="Asian"
    ),
    "Korean": LanguagePack(
        name="Korean",
        code="ko",
        packages=["kiwipiepy"],
        size_mb=90,
        module_check="kiwipiepy",
        category="Asian"
    ),
    "Thai": LanguagePack(
        name="Thai",
        code="th",
        packages=["pythainlp"],
        size_mb=50,
        module_check="pythainlp",
        category="Asian"
    ),

    # === EUROPEAN LANGUAGES (UDPipe models - Python 3.14 compatible) ===
    "English": LanguagePack(
        name="English",
        code="en",
        packages=["ufal.udpipe"],
        size_mb=25,
        module_check="ufal.udpipe",
        udpipe_model="english-ewt-ud-2.5",
        category="European"
    ),
    "German": LanguagePack(
        name="German",
        code="de",
        packages=["ufal.udpipe"],
        size_mb=20,
        module_check="ufal.udpipe",
        udpipe_model="german-gsd-ud-2.5",
        category="European"
    ),
    "French": LanguagePack(
        name="French",
        code="fr",
        packages=["ufal.udpipe"],
        size_mb=20,
        module_check="ufal.udpipe",
        udpipe_model="french-gsd-ud-2.5",
        category="European"
    ),
    "Spanish": LanguagePack(
        name="Spanish",
        code="es",
        packages=["ufal.udpipe"],
        size_mb=25,
        module_check="ufal.udpipe",
        udpipe_model="spanish-ancora-ud-2.5",
        category="European"
    ),
    "Italian": LanguagePack(
        name="Italian",
        code="it",
        packages=["ufal.udpipe"],
        size_mb=20,
        module_check="ufal.udpipe",
        udpipe_model="italian-isdt-ud-2.5",
        category="European"
    ),
    "Portuguese": LanguagePack(
        name="Portuguese",
        code="pt",
        packages=["ufal.udpipe"],
        size_mb=15,
        module_check="ufal.udpipe",
        udpipe_model="portuguese-bosque-ud-2.5",
        category="European"
    ),
    "Dutch": LanguagePack(
        name="Dutch",
        code="nl",
        packages=["ufal.udpipe"],
        size_mb=15,
        module_check="ufal.udpipe",
        udpipe_model="dutch-alpino-ud-2.5",
        category="European"
    ),
    "Polish": LanguagePack(
        name="Polish",
        code="pl",
        packages=["ufal.udpipe"],
        size_mb=25,
        module_check="ufal.udpipe",
        udpipe_model="polish-pdb-ud-2.5",
        category="European"
    ),
    "Russian": LanguagePack(
        name="Russian",
        code="ru",
        packages=["ufal.udpipe"],
        size_mb=50,
        module_check="ufal.udpipe",
        udpipe_model="russian-syntagrus-ud-2.5",
        category="European"
    ),
    "Ukrainian": LanguagePack(
        name="Ukrainian",
        code="uk",
        packages=["ufal.udpipe"],
        size_mb=20,
        module_check="ufal.udpipe",
        udpipe_model="ukrainian-iu-ud-2.5",
        category="European"
    ),
    "Greek": LanguagePack(
        name="Greek",
        code="el",
        packages=["ufal.udpipe"],
        size_mb=15,
        module_check="ufal.udpipe",
        udpipe_model="greek-gdt-ud-2.5",
        category="European"
    ),
    "Romanian": LanguagePack(
        name="Romanian",
        code="ro",
        packages=["ufal.udpipe"],
        size_mb=20,
        module_check="ufal.udpipe",
        udpipe_model="romanian-rrt-ud-2.5",
        category="European"
    ),
    "Croatian": LanguagePack(
        name="Croatian",
        code="hr",
        packages=["ufal.udpipe"],
        size_mb=20,
        module_check="ufal.udpipe",
        udpipe_model="croatian-set-ud-2.5",
        category="European"
    ),
    "Catalan": LanguagePack(
        name="Catalan",
        code="ca",
        packages=["ufal.udpipe"],
        size_mb=25,
        module_check="ufal.udpipe",
        udpipe_model="catalan-ancora-ud-2.5",
        category="European"
    ),
    "Danish": LanguagePack(
        name="Danish",
        code="da",
        packages=["ufal.udpipe"],
        size_mb=15,
        module_check="ufal.udpipe",
        udpipe_model="danish-ddt-ud-2.5",
        category="Scandinavian"
    ),
    "Finnish": LanguagePack(
        name="Finnish",
        code="fi",
        packages=["ufal.udpipe"],
        size_mb=25,
        module_check="ufal.udpipe",
        udpipe_model="finnish-tdt-ud-2.5",
        category="Scandinavian"
    ),
    "Norwegian": LanguagePack(
        name="Norwegian",
        code="nb",
        packages=["ufal.udpipe"],
        size_mb=20,
        module_check="ufal.udpipe",
        udpipe_model="norwegian-bokmaal-ud-2.5",
        category="Scandinavian"
    ),
    "Swedish": LanguagePack(
        name="Swedish",
        code="sv",
        packages=["ufal.udpipe"],
        size_mb=20,
        module_check="ufal.udpipe",
        udpipe_model="swedish-talbanken-ud-2.5",
        category="Scandinavian"
    ),
    "Slovenian": LanguagePack(
        name="Slovenian",
        code="sl",
        packages=["ufal.udpipe"],
        size_mb=20,
        module_check="ufal.udpipe",
        udpipe_model="slovenian-ssj-ud-2.5",
        category="European"
    ),
    "Lithuanian": LanguagePack(
        name="Lithuanian",
        code="lt",
        packages=["ufal.udpipe"],
        size_mb=15,
        module_check="ufal.udpipe",
        udpipe_model="lithuanian-alksnis-ud-2.5",
        category="European"
    ),
    "Macedonian": LanguagePack(
        name="Macedonian",
        code="mk",
        packages=["ufal.udpipe"],
        size_mb=10,
        module_check="ufal.udpipe",
        udpipe_model="macedonian-mtb-ud-2.5",
        category="European"
    ),

    # === OTHER LANGUAGES ===
    "Arabic": LanguagePack(
        name="Arabic",
        code="ar",
        packages=["camel-tools"],
        size_mb=100,
        module_check="camel_tools",
        category="Middle Eastern"
    ),
    "Hebrew": LanguagePack(
        name="Hebrew",
        code="he",
        packages=["ufal.udpipe"],
        size_mb=15,
        module_check="ufal.udpipe",
        udpipe_model="hebrew-htb-ud-2.5",
        category="Middle Eastern"
    ),
    "Indonesian": LanguagePack(
        name="Indonesian",
        code="id",
        packages=["ufal.udpipe"],
        size_mb=15,
        module_check="ufal.udpipe",
        udpipe_model="indonesian-gsd-ud-2.5",
        category="Asian"
    ),
}

# Language categories for UI grouping
LANGUAGE_CATEGORIES = ["Asian", "European", "Scandinavian", "Middle Eastern", "Other"]

# Language detection patterns
UNICODE_RANGES = {
    "Vietnamese": [
        (0x1EA0, 0x1EF9),  # Vietnamese precomposed
    ],
    "Japanese": [
        (0x3040, 0x309F),  # Hiragana
        (0x30A0, 0x30FF),  # Katakana
    ],
    "Chinese (Simplified)": [
        (0x4E00, 0x9FFF),  # CJK Unified Ideographs
        (0x3400, 0x4DBF),  # CJK Extension A
    ],
    "Chinese (Traditional)": [
        (0x4E00, 0x9FFF),  # CJK Unified Ideographs
        (0x3400, 0x4DBF),  # CJK Extension A
    ],
    "Korean": [
        (0xAC00, 0xD7AF),  # Hangul Syllables
        (0x1100, 0x11FF),  # Hangul Jamo
    ],
    "Thai": [
        (0x0E00, 0x0E7F),  # Thai
    ],
    "Arabic": [
        (0x0600, 0x06FF),  # Arabic
        (0x0750, 0x077F),  # Arabic Supplement
    ],
    "Hebrew": [
        (0x0590, 0x05FF),  # Hebrew
    ],
    "Russian": [
        (0x0400, 0x04FF),  # Cyrillic
    ],
    "Greek": [
        (0x0370, 0x03FF),  # Greek and Coptic
    ],
}

# Vietnamese diacritics for detection
VIETNAMESE_CHARS = set('àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ'
                       'ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ')


class NLPManager:
    """Manages NLP language pack installation and tokenization."""

    def __init__(self, config=None):
        """Initialize NLP Manager.

        Args:
            config: Config instance for persisting installed languages
        """
        self.config = config
        self._tokenizers: Dict[str, any] = {}
        self._installed_cache: Dict[str, bool] = {}
        self._spacy_nlp_cache: Dict[str, any] = {}  # Cache loaded spaCy models
        self._udpipe_cache: Dict[str, any] = {}  # Cache loaded UDPipe models

    def set_config(self, config):
        """Set config reference."""
        self.config = config

    def is_installed(self, language: str) -> bool:
        """Check if a language pack is installed.

        Args:
            language: Language name (e.g., "Vietnamese", "English")

        Returns:
            True if the language pack is installed
        """
        if language in self._installed_cache:
            return self._installed_cache[language]

        pack = LANGUAGE_PACKS.get(language)
        if not pack:
            return False

        try:
            # Invalidate Python's import cache to detect newly installed packages
            importlib.invalidate_caches()

            # Remove module from sys.modules if previously imported (allows re-detection)
            module_name = pack.module_check
            if module_name in sys.modules:
                del sys.modules[module_name]

            importlib.import_module(pack.module_check)

            # For spaCy languages, also check if model is downloaded
            if pack.spacy_model:
                import spacy
                try:
                    spacy.load(pack.spacy_model)
                except OSError:
                    self._installed_cache[language] = False
                    return False

            # For UDPipe languages, check if model file exists
            if pack.udpipe_model:
                import os
                model_path = get_udpipe_model_path(pack.udpipe_model)
                if not os.path.exists(model_path):
                    self._installed_cache[language] = False
                    return False

            self._installed_cache[language] = True
            return True
        except ImportError:
            self._installed_cache[language] = False
            return False
        except Exception as e:
            # Catch any other exception (permission errors, etc.)
            logging.warning(f"Error checking {language} installation: {e}")
            self._installed_cache[language] = False
            return False

    def is_any_installed(self) -> bool:
        """Check if any language pack is installed.

        Returns:
            True if at least one language pack is installed
        """
        return len(self.get_installed_languages()) > 0

    def get_installed_languages(self) -> List[str]:
        """Get list of installed language names.

        Returns:
            List of installed language names
        """
        installed = []
        for language in LANGUAGE_PACKS:
            try:
                if self.is_installed(language):
                    installed.append(language)
            except Exception as e:
                logging.warning(f"Error checking if {language} is installed: {e}")
                # Skip this language, don't crash
                continue
        return installed

    def get_available_languages(self) -> List[str]:
        """Get list of all available language names.

        Returns:
            List of all supported language names
        """
        return list(LANGUAGE_PACKS.keys())

    def get_languages_by_category(self) -> Dict[str, List[str]]:
        """Get languages grouped by category.

        Returns:
            Dict mapping category name to list of language names
        """
        result = {cat: [] for cat in LANGUAGE_CATEGORIES}
        for lang_name, pack in LANGUAGE_PACKS.items():
            cat = pack.category if pack.category in result else "Other"
            result[cat].append(lang_name)

        # Sort languages within each category
        for cat in result:
            result[cat].sort()

        # Remove empty categories
        return {k: v for k, v in result.items() if v}

    def get_pack_info(self, language: str) -> Optional[LanguagePack]:
        """Get language pack info.

        Args:
            language: Language name

        Returns:
            LanguagePack info or None
        """
        return LANGUAGE_PACKS.get(language)

    def install(self, language: str,
                progress_callback: Optional[Callable[[str, int], None]] = None) -> Tuple[bool, str]:
        """Install a language pack.

        Args:
            language: Language name (e.g., "Vietnamese")
            progress_callback: Callback for progress updates (message, percentage)

        Returns:
            Tuple of (success, error_message)
        """
        pack = LANGUAGE_PACKS.get(language)
        if not pack:
            return False, f"Unknown language: {language}"

        try:
            total_steps = len(pack.packages) + (1 if pack.post_install else 0)
            current_step = 0

            # Install pip packages
            for package in pack.packages:
                current_step += 1
                progress = int((current_step / total_steps) * 80)  # 0-80%

                if progress_callback:
                    progress_callback(f"Installing {package}...", progress)

                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", package, "--quiet"],
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )

                if result.returncode != 0:
                    error_msg = result.stderr or f"Failed to install {package}"
                    logging.error(f"pip install error: {error_msg}")
                    return False, error_msg

            # Run post-install command if needed (e.g., download spaCy model)
            if pack.post_install:
                if progress_callback:
                    progress_callback("Downloading language model...", 85)

                result = subprocess.run(
                    pack.post_install,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=600  # 10 minute timeout for model download
                )

                if result.returncode != 0:
                    error_msg = result.stderr or "Failed to download language model"
                    logging.error(f"Post-install error: {error_msg}")
                    return False, error_msg

            # Download UDPipe model if needed
            if pack.udpipe_model:
                if progress_callback:
                    progress_callback("Downloading UDPipe model...", 85)

                success, error = self._download_udpipe_model(pack.udpipe_model)
                if not success:
                    return False, error

            # Clear cache and update config
            self._installed_cache.pop(language, None)
            self._tokenizers.pop(language, None)
            self._spacy_nlp_cache.pop(pack.spacy_model, None)

            if self.config:
                installed = self.config.get('nlp_installed', [])
                if language not in installed:
                    installed.append(language)
                    self.config.set('nlp_installed', installed)

            if progress_callback:
                progress_callback(f"{language} installed successfully!", 100)

            logging.info(f"Successfully installed {language} NLP pack")
            return True, ""

        except subprocess.TimeoutExpired:
            return False, "Installation timed out. Please check your internet connection."
        except Exception as e:
            logging.error(f"Install error for {language}: {e}")
            return False, str(e)

    def _download_udpipe_model(self, model_name: str) -> Tuple[bool, str]:
        """Download UDPipe model from LINDAT repository.

        Args:
            model_name: UDPipe model name (e.g., "english-ewt-ud-2.5")

        Returns:
            Tuple of (success, error_message)
        """
        import os
        import urllib.request
        import urllib.error

        url = UDPIPE_MODEL_URLS.get(model_name)
        if not url:
            return False, f"Unknown UDPipe model: {model_name}"

        model_path = get_udpipe_model_path(model_name)

        # Check if already downloaded
        if os.path.exists(model_path):
            logging.info(f"UDPipe model already exists: {model_path}")
            return True, ""

        try:
            # Create models directory
            models_dir = get_udpipe_model_dir()
            os.makedirs(models_dir, exist_ok=True)

            logging.info(f"Downloading UDPipe model from: {url}")

            # Try download with SSL verification first
            try:
                urllib.request.urlretrieve(url, model_path)
            except urllib.error.URLError as ssl_error:
                # If SSL fails (common on corporate networks), try without verification
                if "CERTIFICATE_VERIFY_FAILED" in str(ssl_error) or "SSL" in str(ssl_error):
                    logging.warning("SSL verification failed, retrying without verification")
                    import ssl
                    ssl_context = ssl.create_default_context()
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                    with urllib.request.urlopen(url, context=ssl_context) as response:
                        with open(model_path, 'wb') as out_file:
                            out_file.write(response.read())
                else:
                    raise

            logging.info(f"UDPipe model downloaded to: {model_path}")
            return True, ""

        except urllib.error.URLError as e:
            error_msg = f"Failed to download UDPipe model: {e}"
            logging.error(error_msg)
            # Clean up partial download
            if os.path.exists(model_path):
                os.remove(model_path)
            return False, error_msg
        except Exception as e:
            error_msg = f"Error downloading UDPipe model: {e}"
            logging.error(error_msg)
            if os.path.exists(model_path):
                os.remove(model_path)
            return False, error_msg

    def uninstall(self, language: str,
                  progress_callback: Optional[Callable[[str, int], None]] = None) -> Tuple[bool, str]:
        """Uninstall a language pack.

        Actually removes pip packages and UDPipe/spaCy models.
        Shared packages (like ufal.udpipe) are NOT removed since they may be used
        by other languages.

        Args:
            language: Language name
            progress_callback: Callback for progress updates (message, percentage)

        Returns:
            Tuple of (success, error_message)
        """
        pack = LANGUAGE_PACKS.get(language)
        if not pack:
            return False, f"Unknown language: {language}"

        logging.info(f"=== Starting uninstall of {language} ===")

        try:
            # 0. FIRST: Clear caches and remove from sys.modules to release file locks
            #    This MUST happen BEFORE pip uninstall or files may be locked
            self._installed_cache.pop(language, None)
            self._tokenizers.pop(language, None)
            if pack.spacy_model:
                self._spacy_nlp_cache.pop(pack.spacy_model, None)

            # Remove module from sys.modules to release file handles
            module_name = pack.module_check
            modules_to_remove = [key for key in list(sys.modules.keys())
                               if key == module_name or key.startswith(f"{module_name}.")]
            for mod in modules_to_remove:
                try:
                    del sys.modules[mod]
                except KeyError:
                    pass
            if modules_to_remove:
                logging.info(f"Released {len(modules_to_remove)} modules from memory for {language}")

            # Force garbage collection to release any remaining handles
            gc.collect()

            # Clear UDPipe cache if present
            if pack.udpipe_model and pack.udpipe_model in self._udpipe_cache:
                del self._udpipe_cache[pack.udpipe_model]

            # Packages that are shared between languages - don't uninstall these
            shared_packages = {'spacy', 'spacy-pkuseg', 'ufal.udpipe'}

            total_steps = len(pack.packages) + (1 if pack.spacy_model else 0) + (1 if pack.udpipe_model else 0)
            current_step = 0

            # 1. Remove UDPipe model file if present
            if pack.udpipe_model:
                import os
                current_step += 1
                progress = int((current_step / total_steps) * 80)

                if progress_callback:
                    progress_callback(f"Removing UDPipe model...", progress)

                model_path = get_udpipe_model_path(pack.udpipe_model)
                if os.path.exists(model_path):
                    try:
                        os.remove(model_path)
                        logging.info(f"Removed UDPipe model: {model_path}")
                    except Exception as e:
                        logging.warning(f"Could not remove UDPipe model {model_path}: {e}")

            # 3. Uninstall spaCy model if present (but not the spacy package itself)
            if pack.spacy_model:
                current_step += 1
                progress = int((current_step / total_steps) * 80)

                if progress_callback:
                    progress_callback(f"Removing {pack.spacy_model}...", progress)

                logging.info(f"Running: pip uninstall {pack.spacy_model} -y")
                # Use Popen for more control over timeout
                # CREATE_NO_WINDOW on Windows to prevent console popup
                creation_flags = 0x08000000 if sys.platform == 'win32' else 0  # CREATE_NO_WINDOW
                proc = subprocess.Popen(
                    [sys.executable, "-m", "pip", "uninstall", pack.spacy_model, "-y"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=creation_flags
                )
                try:
                    _, stderr = proc.communicate(timeout=60)
                    logging.info(f"pip uninstall {pack.spacy_model} returned: {proc.returncode}")
                    if proc.returncode != 0:
                        logging.warning(f"Could not uninstall spaCy model {pack.spacy_model}: {stderr}")
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate()  # Clean up
                    logging.error(f"Timeout uninstalling {pack.spacy_model}")

            # 4. Uninstall pip packages (only those NOT shared)
            for package in pack.packages:
                if package not in shared_packages:
                    current_step += 1
                    progress = int((current_step / total_steps) * 80)

                    if progress_callback:
                        progress_callback(f"Removing {package}...", progress)

                    logging.info(f"Running: pip uninstall {package} -y")
                    # Use Popen for more control over timeout
                    # CREATE_NO_WINDOW on Windows to prevent console popup
                    creation_flags = 0x08000000 if sys.platform == 'win32' else 0
                    proc = subprocess.Popen(
                        [sys.executable, "-m", "pip", "uninstall", package, "-y"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        creationflags=creation_flags
                    )
                    try:
                        _, stderr = proc.communicate(timeout=60)
                        logging.info(f"pip uninstall {package} returned: {proc.returncode}")
                        if proc.returncode != 0:
                            logging.warning(f"Could not uninstall {package}: {stderr}")
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.communicate()  # Clean up
                        logging.error(f"Timeout uninstalling {package}")

            # 5. Force is_installed() to return False by caching False
            self._installed_cache[language] = False

            # 6. Update config
            if self.config:
                installed = self.config.get('nlp_installed', [])
                if language in installed:
                    installed.remove(language)
                    self.config.set('nlp_installed', installed)

            if progress_callback:
                progress_callback(f"{language} uninstalled successfully!", 100)

            logging.info(f"=== Successfully uninstalled {language} NLP pack ===")
            return True, ""

        except subprocess.TimeoutExpired as e:
            logging.error(f"=== Uninstall timeout for {language}: {e} ===")
            return False, "Uninstall timed out."
        except Exception as e:
            logging.error(f"Uninstall error for {language}: {e}")
            return False, str(e)

    def detect_language(self, text: str) -> Tuple[str, float]:
        """Detect language of text.

        Args:
            text: Text to analyze

        Returns:
            Tuple of (language_name, confidence) where confidence is 0.0-1.0
        """
        if not text or not text.strip():
            return "Unknown", 0.0

        text = text.strip()
        char_counts = {lang: 0 for lang in LANGUAGE_PACKS}
        total_chars = 0
        latin_chars = 0

        for char in text:
            if char.isspace():
                continue
            total_chars += 1
            code = ord(char)

            # Check Vietnamese first (Latin-based with diacritics)
            if char in VIETNAMESE_CHARS:
                char_counts["Vietnamese"] += 2  # Weight Vietnamese higher

            # Check Unicode ranges
            for lang, ranges in UNICODE_RANGES.items():
                for start, end in ranges:
                    if start <= code <= end:
                        char_counts[lang] += 1
                        break

            # Latin characters (could be many European languages)
            if 0x0041 <= code <= 0x007A:  # A-Z, a-z
                latin_chars += 1
                if char_counts["Vietnamese"] > 0:
                    char_counts["Vietnamese"] += 0.5
                else:
                    char_counts["English"] += 0.3
                    char_counts["French"] += 0.3
                    char_counts["German"] += 0.3
                    char_counts["Spanish"] += 0.3

        if total_chars == 0:
            return "Unknown", 0.0

        # Find language with highest count
        max_lang = max(char_counts, key=char_counts.get)
        max_count = char_counts[max_lang]

        if max_count == 0:
            return "Unknown", 0.0

        confidence = min(max_count / total_chars, 1.0)

        # Disambiguate Chinese vs Japanese (both use CJK)
        if max_lang in ["Chinese (Simplified)", "Chinese (Traditional)", "Japanese"]:
            hiragana_count = sum(1 for c in text if 0x3040 <= ord(c) <= 0x30FF)
            if hiragana_count > 0:
                max_lang = "Japanese"
                confidence = min(confidence + 0.2, 1.0)
            else:
                max_lang = "Chinese (Simplified)"

        # For pure Latin text (European languages), prioritize installed languages
        # This solves the problem where multiple languages have equal scores
        if latin_chars > 0 and latin_chars / total_chars > 0.8:
            # Text is mostly Latin - check which European languages are installed
            european_langs = ["English", "German", "French", "Spanish", "Italian",
                            "Portuguese", "Dutch", "Polish", "Danish", "Swedish",
                            "Norwegian", "Finnish", "Romanian", "Croatian", "Catalan",
                            "Slovenian", "Lithuanian", "Macedonian", "Indonesian"]
            installed_european = [lang for lang in european_langs if self.is_installed(lang)]

            if installed_european:
                # If only one European language is installed, use it with high confidence
                if len(installed_european) == 1:
                    max_lang = installed_european[0]
                    confidence = 0.85  # High confidence for single installed language
                else:
                    # Multiple European languages installed - pick the one with highest score
                    # among installed languages
                    best_installed = max(installed_european, key=lambda l: char_counts.get(l, 0))
                    if char_counts.get(best_installed, 0) > 0:
                        max_lang = best_installed
                        confidence = 0.75  # Medium-high confidence

        return max_lang, confidence

    def tokenize(self, text: str, language: str) -> List[str]:
        """Tokenize text using appropriate NLP library.

        Args:
            text: Text to tokenize
            language: Language name

        Returns:
            List of tokens (words/phrases)
        """
        if not self.is_installed(language):
            return self._simple_tokenize(text)

        # Lazy load tokenizer
        if language not in self._tokenizers:
            self._load_tokenizer(language)

        tokenizer = self._tokenizers.get(language)
        if not tokenizer:
            return self._simple_tokenize(text)

        try:
            return tokenizer(text)
        except Exception as e:
            logging.error(f"Tokenization error for {language}: {e}")
            return self._simple_tokenize(text)

    def _simple_tokenize(self, text: str) -> List[str]:
        """Simple whitespace-based tokenization fallback.

        Args:
            text: Text to tokenize

        Returns:
            List of tokens
        """
        return re.findall(r'\S+', text)

    def _tokenize_with_udpipe(self, text: str, model) -> List[str]:
        """Tokenize text using UDPipe model with compound word grouping.

        Uses UDPipe's dependency parsing to identify and group:
        - Phrasal verbs: "give up", "break down"
        - Compound nouns: "ice cream", "New York"
        - Named entities: "Osaka Castle", "John Smith"

        Args:
            text: Text to tokenize
            model: Loaded UDPipe model

        Returns:
            List of tokens with multi-word expressions merged
        """
        try:
            from ufal.udpipe import Pipeline, ProcessingError

            # Create pipeline for full parsing (tokenize + tag + parse)
            # This gives us dependency relations needed for compound detection
            pipeline = Pipeline(model, "tokenize", Pipeline.DEFAULT, Pipeline.DEFAULT, "conllu")
            error = ProcessingError()

            # Process text
            processed = pipeline.process(text, error)

            if error.occurred():
                logging.warning(f"UDPipe processing error: {error.message}")
                return self._simple_tokenize(text)

            # Parse CoNLL-U format to extract tokens with dependency info
            parsed_tokens = self._parse_conllu(processed)

            if not parsed_tokens:
                return self._simple_tokenize(text)

            # Group multi-word expressions based on dependency relations
            grouped_tokens = self._group_multi_word_expressions(parsed_tokens)

            return grouped_tokens if grouped_tokens else self._simple_tokenize(text)

        except Exception as e:
            logging.error(f"UDPipe tokenization error: {e}")
            return self._simple_tokenize(text)

    def _parse_conllu(self, conllu_output: str) -> List[ParsedToken]:
        """Parse CoNLL-U output into structured tokens.

        CoNLL-U format columns (tab-separated):
        0: ID (word index in sentence, 1-based)
        1: FORM (word form/surface)
        2: LEMMA (lemma/dictionary form)
        3: UPOS (universal POS tag)
        4: XPOS (language-specific POS tag)
        5: FEATS (morphological features)
        6: HEAD (head token ID, 0 = root)
        7: DEPREL (dependency relation to head)
        8: DEPS (enhanced dependencies)
        9: MISC (miscellaneous)

        Args:
            conllu_output: Raw CoNLL-U formatted string from UDPipe

        Returns:
            List of ParsedToken objects with dependency information
        """
        tokens = []
        # Track sentence offset to make token IDs unique across sentences
        # Each sentence in CoNLL-U has IDs starting from 1, so we need to add offset
        sentence_offset = 0
        last_token_id = 0

        for line in conllu_output.split('\n'):
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue

            parts = line.split('\t')

            # Must have at least 8 columns for dependency info
            if len(parts) < 8:
                continue

            # Skip multi-word tokens (ID like "1-2") and empty nodes (ID like "1.1")
            if '-' in parts[0] or '.' in parts[0]:
                continue

            # Check if first column is a valid integer (token ID)
            try:
                token_id = int(parts[0])
            except ValueError:
                continue

            # Detect new sentence (token ID resets to 1 or lower than previous)
            if token_id <= last_token_id:
                # New sentence starts - update offset
                sentence_offset = len(tokens)

            last_token_id = token_id

            # Parse HEAD (could be "_" if not available)
            try:
                head = int(parts[6]) if parts[6] != '_' else 0
            except ValueError:
                head = 0

            # Get dependency relation
            deprel = parts[7] if parts[7] != '_' else ''

            # Get universal POS tag (column 3)
            upos = parts[3] if parts[3] != '_' else ''

            # Make IDs unique across sentences by adding offset
            global_id = sentence_offset + token_id
            global_head = sentence_offset + head if head > 0 else 0

            token = ParsedToken(
                id=global_id,
                form=parts[1],
                head=global_head,
                deprel=deprel,
                upos=upos
            )
            tokens.append(token)

        return tokens

    def _validate_compound_pos(self, dependent: ParsedToken, head: ParsedToken) -> bool:
        """Validate if dependent-head pair should be grouped based on POS tags.

        Uses COMPOUND_POS_CONSTRAINTS to determine if the POS combination is valid.
        This prevents incorrect groupings like "Osaka fast" (PROPN + ADJ).

        Args:
            dependent: The dependent token (e.g., "fast" in "Osaka fast")
            head: The head token (e.g., "Osaka" in "Osaka fast")

        Returns:
            True if the pair should be grouped, False otherwise
        """
        deprel = dependent.deprel
        if not deprel:
            return False

        deprel_base = deprel.split(':')[0]

        # Get constraint for this relation
        constraint = None
        if deprel in COMPOUND_POS_CONSTRAINTS:
            constraint = COMPOUND_POS_CONSTRAINTS[deprel]
        elif deprel_base in COMPOUND_POS_CONSTRAINTS:
            constraint = COMPOUND_POS_CONSTRAINTS[deprel_base]

        # No constraint = always allow (fixed, goeswith, flat:foreign)
        if constraint is None:
            return True

        # Get POS tags
        dep_pos = dependent.upos
        head_pos = head.upos

        # Skip if either POS is missing
        if not dep_pos or not head_pos:
            return False

        # For 'flat' relations: both must be PROPN (proper names only)
        if deprel_base == 'flat':
            return dep_pos == 'PROPN' and head_pos == 'PROPN'

        # For 'compound': validate based on subtype
        if deprel_base == 'compound':
            # compound:prt = phrasal verb particles (head must be VERB)
            if deprel == 'compound:prt':
                return head_pos == 'VERB'
            # Regular compound: both must be noun-like (NOUN, PROPN)
            # Also allow VERB as head (e.g., "ice-skating")
            return dep_pos in constraint and head_pos in {'NOUN', 'PROPN', 'VERB'}

        return True  # Default allow for other relations

    def _group_multi_word_expressions(self, tokens: List[ParsedToken]) -> List[str]:
        """Group tokens that form multi-word expressions based on dependency relations.

        Handles:
        - Phrasal verbs: "give up", "break down" (deprel: compound:prt)
        - Compound nouns: "ice cream", "New York" (deprel: compound, flat)
        - Named entities: "Osaka Castle", "John Smith" (deprel: flat:name)

        Args:
            tokens: List of ParsedToken with dependency information

        Returns:
            List of string tokens with compounds/phrases merged
        """
        if not tokens:
            return []

        # Build a map of token ID to token for quick lookup
        token_map = {t.id: t for t in tokens}

        # Track which tokens have been merged (consumed)
        consumed = set()

        # Build groups: head_id -> [dependent tokens that should be merged]
        groups = {}
        for token in tokens:
            # Check if this token should be merged with its head
            # Also check for subtypes like "compound:prt"
            deprel_base = token.deprel.split(':')[0] if token.deprel else ''
            if (token.deprel in COMPOUND_RELATIONS or
                deprel_base in COMPOUND_RELATIONS) and token.head in token_map:

                # Validate POS compatibility before grouping
                head_token = token_map[token.head]
                if not self._validate_compound_pos(token, head_token):
                    continue  # Skip invalid groupings (e.g., "Osaka fast", "butterfly because")

                head_id = token.head
                if head_id not in groups:
                    groups[head_id] = []
                groups[head_id].append(token)
                consumed.add(token.id)

        # Build result by iterating through tokens in order
        result = []
        for token in tokens:
            if token.id in consumed:
                # This token is part of a compound and will be included with its head
                continue

            if token.id in groups:
                # This token is the head of a compound - merge with dependents
                # Collect all parts (head + dependents) and sort by position
                all_parts = [token] + groups[token.id]
                all_parts.sort(key=lambda t: t.id)

                # Merge into single token text
                merged_text = ' '.join(t.form for t in all_parts)
                result.append(merged_text)
            else:
                # Single token - not part of any compound
                result.append(token.form)

        return result

    def _load_tokenizer(self, language: str):
        """Load tokenizer for a language.

        Args:
            language: Language name
        """
        pack = LANGUAGE_PACKS.get(language)
        if not pack:
            self._tokenizers[language] = None
            return

        try:
            # Specialized tokenizers for Asian languages
            if language == "Vietnamese":
                from underthesea import word_tokenize
                self._tokenizers[language] = lambda t: word_tokenize(t)

            elif language == "Japanese":
                import fugashi
                tagger = fugashi.Tagger()
                self._tokenizers[language] = lambda t: [word.surface for word in tagger(t)]

            elif language in ["Chinese (Simplified)", "Chinese (Traditional)"]:
                import jieba
                self._tokenizers[language] = lambda t: list(jieba.cut(t))

            elif language == "Korean":
                from kiwipiepy import Kiwi
                kiwi = Kiwi()
                self._tokenizers[language] = lambda t: [token.form for token in kiwi.tokenize(t)]

            elif language == "Thai":
                from pythainlp.tokenize import word_tokenize as thai_tokenize
                self._tokenizers[language] = lambda t: thai_tokenize(t)

            elif language == "Arabic":
                from camel_tools.tokenizers.word import simple_word_tokenize
                self._tokenizers[language] = lambda t: simple_word_tokenize(t)

            # spaCy-based tokenizers
            elif pack.spacy_model:
                import spacy
                if pack.spacy_model not in self._spacy_nlp_cache:
                    self._spacy_nlp_cache[pack.spacy_model] = spacy.load(pack.spacy_model)
                nlp = self._spacy_nlp_cache[pack.spacy_model]
                self._tokenizers[language] = lambda t, nlp=nlp: [token.text for token in nlp(t)]

            # UDPipe-based tokenizers
            elif pack.udpipe_model:
                import os
                from ufal.udpipe import Model, Pipeline, ProcessingError
                model_path = get_udpipe_model_path(pack.udpipe_model)
                if os.path.exists(model_path):
                    model = Model.load(model_path)
                    if model:
                        # Cache the model
                        self._udpipe_cache[pack.udpipe_model] = model
                        self._tokenizers[language] = lambda t, m=model: self._tokenize_with_udpipe(t, m)
                    else:
                        logging.error(f"Failed to load UDPipe model: {model_path}")
                        self._tokenizers[language] = self._simple_tokenize
                else:
                    logging.warning(f"UDPipe model not found: {model_path}")
                    self._tokenizers[language] = self._simple_tokenize

            else:
                # Fallback to simple tokenization
                self._tokenizers[language] = self._simple_tokenize

            logging.info(f"Loaded tokenizer for {language}")

        except Exception as e:
            logging.error(f"Failed to load tokenizer for {language}: {e}")
            self._tokenizers[language] = None

    def verify_installation(self, language: str) -> bool:
        """Verify that a language pack is properly installed and working.

        Args:
            language: Language name

        Returns:
            True if installation is valid and working
        """
        if not self.is_installed(language):
            return False

        try:
            # Try to tokenize a simple test string
            test_strings = {
                "Vietnamese": "Xin chào",
                "English": "Hello world",
                "Japanese": "こんにちは",
                "Chinese (Simplified)": "你好世界",
                "Chinese (Traditional)": "你好世界",
                "Korean": "안녕하세요",
                "Thai": "สวัสดี",
                "Arabic": "مرحبا",
                "Hebrew": "שלום",
                "Russian": "Привет",
                "German": "Hallo Welt",
                "French": "Bonjour monde",
                "Spanish": "Hola mundo",
            }

            test_text = test_strings.get(language, "test")
            tokens = self.tokenize(test_text, language)

            return len(tokens) > 0

        except Exception as e:
            logging.error(f"Verification failed for {language}: {e}")
            return False

    def get_total_installed_size(self) -> int:
        """Get total size of installed language packs in MB.

        Returns:
            Total size in MB
        """
        total = 0
        for language in self.get_installed_languages():
            pack = LANGUAGE_PACKS.get(language)
            if pack:
                total += pack.size_mb
        return total

    def get_language_count(self) -> Tuple[int, int]:
        """Get count of installed and available languages.

        Returns:
            Tuple of (installed_count, total_count)
        """
        return len(self.get_installed_languages()), len(LANGUAGE_PACKS)


# Global instance (will be initialized with config in app.py)
nlp_manager = NLPManager()
