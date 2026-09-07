"""
Quick non-interactive smoke test for PP-OCRv5 setup.
Run with: ./venv/bin/python3 test_paddle_v5.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/src')

results = []

# Test 1: paddleocr import
try:
    from paddleocr import TextRecognition, TextDetection
    results.append("✅ paddleocr TextRecognition + TextDetection import OK")
    PADDLE_OK = True
except ImportError as e:
    results.append(f"❌ paddleocr import FAILED: {e}")
    PADDLE_OK = False

# Test 2: config_v5 import
try:
    import config_v5 as cfg
    results.append(f"✅ config_v5 loaded OK")
    results.append(f"   ENABLE_PADDLE_OCR     = {cfg.ENABLE_PADDLE_OCR}")
    results.append(f"   PADDLE_REC_MODEL      = {cfg.PADDLE_REC_MODEL}")
    results.append(f"   PADDLE_DET_MODEL      = {cfg.PADDLE_DET_MODEL}")
    results.append(f"   PADDLE_CONFIDENCE_THRESH = {cfg.PADDLE_CONFIDENCE_THRESH}")
    results.append(f"   PADDLE_MIN_LINE_RATIO = {cfg.PADDLE_MIN_LINE_RATIO}")
    results.append(f"   HYBRID_PRIMARY        = {cfg.HYBRID_PRIMARY}")
    results.append(f"   HYBRID_FALLBACK       = {cfg.HYBRID_FALLBACK}")
except Exception as e:
    results.append(f"❌ config_v5 FAILED: {e}")

# Test 3: paddle_v5_processor import
try:
    from paddle_v5_processor import PaddleV5Processor, PADDLEOCR_AVAILABLE
    results.append(f"✅ paddle_v5_processor import OK | PADDLEOCR_AVAILABLE={PADDLEOCR_AVAILABLE}")
except Exception as e:
    results.append(f"❌ paddle_v5_processor import FAILED: {e}")

# Test 4: ocr_factory with paddle engine
try:
    import config_v5 as config_module
    import sys
    sys.modules['config'] = config_module  # inject config_v5 as active config
    from ocr_factory import OCRFactory
    engines = OCRFactory.get_available_engines()
    results.append(f"✅ OCRFactory.get_available_engines() = {engines}")
    if 'paddle' in engines:
        results.append("✅ 'paddle' engine is in available engines list")
    else:
        results.append("⚠️  'paddle' not in engines — check ENABLE_PADDLE_OCR and paddleocr install")
except Exception as e:
    results.append(f"❌ ocr_factory test FAILED: {e}")

# Test 5: Models on disk
import pathlib
paddlex_models = pathlib.Path.home() / '.paddlex' / 'official_models'
for model in ['te_PP-OCRv5_mobile_rec', 'PP-OCRv5_server_det']:
    model_path = paddlex_models / model / 'inference.pdiparams'
    if model_path.exists():
        size_mb = model_path.stat().st_size / (1024*1024)
        results.append(f"✅ Model on disk: {model} ({size_mb:.1f} MB)")
    else:
        results.append(f"❌ Model NOT found: {model_path}")

# Test 6: Fallback path — PaddleV5Processor with ENABLE_PADDLE_OCR=False
try:
    import config as base_cfg
    original = getattr(base_cfg, 'ENABLE_PADDLE_OCR', None)
    base_cfg.ENABLE_PADDLE_OCR = False
    proc = PaddleV5Processor(language='te', config=base_cfg)
    results.append(f"✅ Fallback-only mode: paddle_enabled={proc.paddle_enabled} (should be False)")
    if original is not None:
        base_cfg.ENABLE_PADDLE_OCR = original
except Exception as e:
    results.append(f"❌ Fallback mode test FAILED: {e}")

# Print results
print("\n" + "="*60)
print("PP-OCRv5 Implementation Verification")
print("="*60)
for r in results:
    print(r)
print("="*60)
print("DONE")
