from hashlib import sha256
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def test_corrupt_source_is_never_cached_and_verified_cache_needs_no_network(tmp_path):
    from fetch_recognition_photos import cache_image

    data = b"expected image"
    target = tmp_path / "image.jpg"
    with pytest.raises(ValueError, match="checksum"):
        cache_image(target, sha256(data).hexdigest(), {}, lambda _: b"new bytes")
    assert not target.exists()
    cache_image(target, sha256(data).hexdigest(), {}, lambda _: data)
    cache_image(target, sha256(data).hexdigest(), {}, lambda _: pytest.fail("cache was valid"))
