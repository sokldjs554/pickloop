"""Contract tests catch label swaps, unknown acceptance, and export drift."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]

def fixture_crop(kind):
    image = Image.new('RGB', (96, 96), (57, 59, 63))
    draw = ImageDraw.Draw(image)
    draw.rectangle((15, 12, 81, 84), fill=(190, 27, 35) if kind != 'unknown' else (30, 160, 55))
    if kind == 'a':
        draw.rectangle((16, 39, 80, 57), fill=(240, 240, 232))
    elif kind == 'b':
        draw.rectangle((16, 29, 80, 39), fill=(240, 240, 232))
        draw.rectangle((16, 57, 80, 67), fill=(240, 240, 232))
    else:
        draw.line((22, 20, 75, 77), fill='white', width=11)
        draw.line((75, 20, 22, 77), fill='white', width=11)
    return np.asarray(image)

def test_appearance_module_is_available():
    assert importlib.util.find_spec('pickloop.vision_model') is not None

def test_predict_uses_learned_pixels_and_rejects_unknown():
    from pickloop.vision_model import AppearanceModel
    model = AppearanceModel()
    result = model.predict([fixture_crop('a'), fixture_crop('b'), fixture_crop('unknown')])
    assert [item['sku'] for item in result] == ['SKU-RED-A', 'SKU-RED-B', 'UNKNOWN']
    rotated = np.rot90(fixture_crop('b')).copy()
    assert model.predict([rotated])[0]['sku'] == 'SKU-RED-B'
    assert min(item['confidence'] for item in result[:2]) > .8
    assert len(result[0]['embedding']) == 32
    assert result[0]['embedding'] != result[1]['embedding']
    assert all(np.isfinite(item['distance']) and 0 <= item['confidence'] <= 1 for item in result)
    assert model.predict(np.empty((0, 64, 64, 3), dtype=np.uint8)) == []

def test_invalid_input_does_not_silently_cast_float_pixels():
    from pickloop.vision_model import AppearanceModel
    model = AppearanceModel()
    with pytest.raises(ValueError, match='uint8'):
        model.predict([fixture_crop('a').astype(np.float32)])
    with pytest.raises(ValueError, match='RGB'):
        model.predict([np.zeros((12, 12), dtype=np.uint8)])

def test_torchscript_preserves_logits_and_embeddings():
    import torch
    from pickloop.vision_model import AppearanceModel, crops_to_tensor
    model = AppearanceModel()
    exported = torch.jit.load(str(ROOT / 'models' / 'appearance.ts'), map_location='cpu').eval()
    images = crops_to_tensor([fixture_crop('a'), fixture_crop('b'), fixture_crop('unknown')])
    with torch.inference_mode():
        expected = model.network(images)
        actual = exported(images)
    for left, right in zip(expected, actual):
        torch.testing.assert_close(left, right, rtol=1e-5, atol=1e-6)
