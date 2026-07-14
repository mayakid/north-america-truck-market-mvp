from __future__ import annotations

import hashlib

from crossborder_recommender.cli import _sha256_file


def test_sha256_file_matches_standard_library(tmp_path):
    payload = b"BTS provenance fixture\n"
    path = tmp_path / "fixture.bin"
    path.write_bytes(payload)

    assert _sha256_file(path) == hashlib.sha256(payload).hexdigest()
