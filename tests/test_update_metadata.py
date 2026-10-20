"""Use the EXE's own digest and retain cancellation without Content-Length."""
import io
import json
from unittest.mock import Mock

import pytest

from src.utils import updates


HASH = 'a' * 64
URL = 'https://github.com/example/example/releases/download/v9.9.9/CrossTrans_v9.9.9.exe'


@pytest.mark.parametrize('digest,notes,expected', [
    ('sha256:' + HASH, '', HASH),
    ('sha256:' + HASH, 'SHA256: ' + 'b' * 64, HASH),
    (None, 'SHA256: ' + HASH, HASH),
    ('sha512:' + HASH, 'SHA256: ' + HASH, HASH),
    ('sha256:not-a-hash', '', None),
])
def test_exe_digest_and_legacy_release_notes(monkeypatch, digest, notes, expected):
    class Response(io.BytesIO):
        status = 200
        headers = {}

    metadata = {'tag_name': 'v9.9.9', 'body': notes, 'assets': [
        {'name': 'SHA256SUMS.txt', 'browser_download_url': URL + '.txt', 'digest': 'sha256:' + 'c' * 64},
        {'name': 'CrossTrans_v9.9.9.exe', 'browser_download_url': URL, 'digest': digest},
    ]}
    monkeypatch.setattr(updates.urllib.request, 'urlopen',
                        lambda *_args, **_kwargs: Response(json.dumps(metadata).encode()))
    updater = updates.AutoUpdater()
    result = updater.check_update(max_retries=1)
    assert result['has_update']
    assert updater.exe_url == URL
    assert updater.expected_sha256 == expected


def test_unknown_length_download_still_checks_cancel(monkeypatch, tmp_path):
    class Response(io.BytesIO):
        headers = {}

    monkeypatch.setattr(updates.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(updates.tempfile, 'mkdtemp', lambda **_kwargs: str(tmp_path))
    monkeypatch.setattr(updates.urllib.request, 'urlopen',
                        lambda *_args, **_kwargs: Response(b'x' * 20000))
    updater = updates.AutoUpdater()
    updater.latest_version = '9.9.9'
    updater.exe_url = URL
    progress = Mock(side_effect=updates.DownloadCancelledException('User cancelled'))
    result = updater.download(progress)
    progress.assert_called_once_with(0)
    assert not result['success']
    assert 'cancelled' in result['error']
