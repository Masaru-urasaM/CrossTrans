# -*- mode: python ; coding: utf-8 -*-

# CrossTrans v1.9.6 - PyInstaller Build Configuration
# Build command: pyinstaller CrossTrans.spec --clean --noconfirm

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('src/assets', 'src/assets'),  # Icons and images
    ],
    hiddenimports=[
        # GUI framework
        'ttkbootstrap',
        'ttkbootstrap.dialogs',
        'ttkbootstrap.constants',
        'ttkbootstrap.style',
        'ttkbootstrap.themes',
        'ttkbootstrap.themes.standard',
        'ttkbootstrap.localization',
        'ttkbootstrap.icons',
        'ttkbootstrap.tooltip',
        'ttkbootstrap.scrolled',
        'ttkbootstrap.tableview',
        # Windows APIs
        'win32clipboard',
        'win32con',
        'win32api',
        'pywintypes',
        # Other dependencies
        'keyboard',
        'packaging',
        'packaging.version',
        'config',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary modules to reduce EXE size
        'pytest',
        'pytest_cov',
        'pytest_mock',
        'test',
        'tests',
        # Unused tkinter modules
        'tkinter.test',
        # Unused standard library
        'lib2to3',

        # ============================================
        # Google Generative AI SDK (using REST API instead)
        # ============================================
        'google.generativeai',
        'google.ai',
        'google.api_core',
        'google.auth',
        'google.protobuf',
        'grpc',
        'grpcio',
        'grpcio_status',
        'proto',

        # ============================================
        # NLP packages - downloaded on-demand by user
        # DO NOT bundle in EXE
        # ============================================
        # Core NLP libraries
        'spacy',
        'spacy_legacy',
        'spacy_loggers',
        'jieba',
        'fugashi',
        'unidic',
        'unidic_lite',
        'underthesea',
        'underthesea_core',
        'ufal',
        'ufal.udpipe',
        'pythainlp',
        'kiwipiepy',
        # spaCy dependencies
        'thinc',
        'thinc_apple_ops',
        'cymem',
        'preshed',
        'murmurhash',
        'blis',
        'wasabi',
        'srsly',
        'catalogue',
        'typer',
        'pathy',
        'confection',
        'spacy_pkuseg',
        # Other NLP dependencies
        'sudachipy',
        'sudachidict_core',
        'nagisa',
        'konlpy',
        'mecab',
        'janome',
        'pyvi',
        'pymorphy2',
        'pymorphy3',
        'stanza',
        'nltk',
        'transformers',
        'torch',
        'tensorflow',
        'keras',

        # ============================================
        # Scientific computing - not needed for translation
        # ============================================
        'pandas',
        'pandas._libs',
        'pandas.core',
        'pandas.io',
        'scipy',
        'scipy.linalg',
        'scipy.sparse',
        'scipy.special',
        'scipy.stats',
        'scipy.optimize',
        'scipy.integrate',
        'scipy.interpolate',
        'scipy.signal',
        'scipy.ndimage',
        'scipy.spatial',
        'scipy.constants',
        'scipy.fft',
        'scipy._lib',

        # ============================================
        # Data / filesystem - not needed
        # ============================================
        'fsspec',
        'pyarrow',
        'numba',
        'bottleneck',
        'xarray',
        'h5py',
        'tables',
        'openpyxl',
        'xlrd',
    ],
    noarchive=False,
    optimize=1,  # Basic optimization
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CrossTrans',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='CrossTrans.ico',
)
