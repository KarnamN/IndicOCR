#!/usr/bin/env python3
"""
benchmark_quality.py — Benchmarking OCR Speed & Quality (JiWER)
===============================================================
Compares:
  1. Tesseract OCR (Standard / Enhanced config)
  2. PP-OCRv5 (OpenVINO-accelerated primary)
  3. Comparative Sequence Merge (Tesseract + PP-OCRv5)

Usage:
  python scripts/benchmark_quality.py --image <image_path> [--reference <ref_text_path>] [--dpi 400]
"""

import sys
import os
import time
import argparse
from pathlib import Path
from PIL import Image

# Add src to python path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

# Force config_v5 (PP-OCRv5 mode) as config before loading factories
import config_v5 as config_module
sys.modules['config'] = config_module

from paddle_v5_processor import PaddleV5Processor
from ocr_processor import OCRProcessor
from telugu_post_processor import TeluguPostProcessor
from logging_config import get_logger

# Disable verbose logs for cleaner output
import logging
logging.getLogger('paddle').setLevel(logging.WARNING)
logging.getLogger('ppocr').setLevel(logging.WARNING)

logger = get_logger(__name__)

try:
    import jiwer
    JIWER_AVAILABLE = True
except ImportError:
    JIWER_AVAILABLE = False
    print("⚠️  jiwer library is not installed. WER/CER calculations will be skipped.")


def calculate_metrics(extracted_text, reference_text):
    """Calculate WER and CER using JiWER library."""
    if not JIWER_AVAILABLE or not reference_text:
        return None, None
    
    # Normalize texts slightly to get robust comparisons (e.g. whitespace stripping)
    ref = reference_text.strip()
    hyp = extracted_text.strip()
    
    if not ref:
        return None, None
    
    try:
        # Calculate Word Error Rate (WER)
        wer = jiwer.wer(ref, hyp)
        # Calculate Character Error Rate (CER)
        cer = jiwer.cer(ref, hyp)
        return float(wer), float(cer)
    except Exception as e:
        logger.error(f"Error calculating metrics: {e}")
        return None, None


def main():
    parser = argparse.ArgumentParser(description="Benchmark OCR Engine Speed and Accuracy")
    parser.add_argument('--image', required=True, help="Path to input image for OCR")
    parser.add_argument('--reference', help="Path to text file containing ground-truth transcription")
    parser.add_argument('--dpi', type=int, default=400, help="DPI for preprocessing (default: 400)")
    parser.add_argument('--dict-correction', action='store_true',
                         help="Also benchmark the merged result with Telugu dictionary "
                              "spell-correction enabled (ENABLE_TELUGU_DICTIONARY_CORRECTION), "
                              "to measure its isolated CER/WER impact.")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"❌ Image not found: {image_path}")
        sys.exit(1)

    ref_text = ""
    if args.reference:
        ref_path = Path(args.reference)
        if ref_path.exists():
            ref_text = ref_path.read_text(encoding='utf-8')
            print(f"📖 Loaded ground truth from {ref_path} ({len(ref_text)} characters)")
        else:
            print(f"❌ Reference text file not found: {ref_path}")
            sys.exit(1)

    print(f"🖼️ Loading image: {image_path.name}")
    try:
        img = Image.open(image_path)
    except Exception as e:
        print(f"❌ Failed to load image: {e}")
        sys.exit(1)

    # Instantiate processors
    print("\n🚀 Initializing processors (loading models)...")
    
    # 1. Tesseract
    tess_lang = getattr(config_module, 'DEFAULT_OCR_LANGUAGE', 'tel_best+eng')
    tess_config = getattr(config_module, 'TESSERACT_CONFIG', '--oem 1 --psm 4')
    tess_proc = OCRProcessor(language=tess_lang, config_str=tess_config)
    
    # 2. PaddleV5 Processor (handles fallback & merge as well)
    paddle_proc = PaddleV5Processor(language='te', config=config_module)

    print("\n⏱️ Running Benchmarks...")

    results = {}

    # --- TEST 1: TESSERACT ONLY ---
    print("  🏃 Running Tesseract OCR...")
    start_time = time.time()
    try:
        tess_text = tess_proc.extract_text(img, page_label="Tess_Bench")
        tess_time = time.time() - start_time
        tess_lines = len([l for l in tess_text.splitlines() if l.strip()])
        tess_chars = len(tess_text)
        wer, cer = calculate_metrics(tess_text, ref_text)
        results['tesseract'] = {
            'name': 'Tesseract Only',
            'time': tess_time,
            'chars': tess_chars,
            'lines': tess_lines,
            'wer': wer,
            'cer': cer,
            'text': tess_text
        }
        print(f"     ✓ Completed in {tess_time:.2f}s | Chars: {tess_chars} | Lines: {tess_lines}")
    except Exception as e:
        print(f"     ❌ Tesseract failed: {e}")

    # --- TEST 2: PADDLEOCR (OpenVINO-accelerated) ---
    print("  🏃 Running PaddleOCR (OpenVINO)...")
    start_time = time.time()
    try:
        paddle_text, boxes = paddle_proc._paddle_extract(img)
        paddle_time = time.time() - start_time
        paddle_lines = len([l for l in paddle_text.splitlines() if l.strip()])
        paddle_chars = len(paddle_text)
        wer, cer = calculate_metrics(paddle_text, ref_text)
        results['paddle'] = {
            'name': 'PaddleOCR (OpenVINO)',
            'time': paddle_time,
            'chars': paddle_chars,
            'lines': paddle_lines,
            'wer': wer,
            'cer': cer,
            'text': paddle_text
        }
        print(f"     ✓ Completed in {paddle_time:.2f}s | Chars: {paddle_chars} | Lines: {paddle_lines}")
    except Exception as e:
        print(f"     ❌ PaddleOCR failed: {e}")

    # --- TEST 3: COMPARATIVE MERGE ---
    print("  🏃 Running Comparative Sequence Merge (Tess + Paddle)...")
    start_time = time.time()
    try:
        # Run the full pipeline extract with fallback and merge
        res = paddle_proc.extract_with_fallback(img, preprocess=True, page_label="Merge_Bench")
        merge_time = time.time() - start_time
        merge_text = res.get('text', '')
        merge_lines = len([l for l in merge_text.splitlines() if l.strip()])
        merge_chars = len(merge_text)
        wer, cer = calculate_metrics(merge_text, ref_text)
        results['merged'] = {
            'name': f"Merged ({res.get('engine', 'unknown')})",
            'time': merge_time,
            'chars': merge_chars,
            'lines': merge_lines,
            'wer': wer,
            'cer': cer,
            'text': merge_text
        }
        print(f"     ✓ Completed in {merge_time:.2f}s | Chars: {merge_chars} | Lines: {merge_lines}")
    except Exception as e:
        print(f"     ❌ Merge pipeline failed: {e}")

    # --- TEST 4: MERGED + TELUGU POST-PROCESSING (isolates dictionary-correction impact) ---
    if 'merged' in results:
        merge_text = results['merged']['text']

        print("  🏃 Running Telugu post-processing (dictionary correction OFF)...")
        start_time = time.time()
        proc_off = TeluguPostProcessor(enable_dictionary_correction=False)
        text_off = proc_off.process(merge_text)
        time_off = time.time() - start_time
        wer, cer = calculate_metrics(text_off, ref_text)
        results['postprocessed'] = {
            'name': 'Merged + Post-processing (dict OFF)',
            'time': time_off, 'chars': len(text_off),
            'lines': len([l for l in text_off.splitlines() if l.strip()]),
            'wer': wer, 'cer': cer, 'text': text_off,
        }
        print(f"     ✓ Completed in {time_off:.2f}s | Chars: {len(text_off)}")

        if args.dict_correction:
            print("  🏃 Running Telugu post-processing (dictionary correction ON)...")
            start_time = time.time()
            proc_on = TeluguPostProcessor(enable_dictionary_correction=True)
            text_on = proc_on.process(merge_text)
            time_on = time.time() - start_time
            wer, cer = calculate_metrics(text_on, ref_text)
            results['postprocessed_dict'] = {
                'name': 'Merged + Post-processing (dict ON)',
                'time': time_on, 'chars': len(text_on),
                'lines': len([l for l in text_on.splitlines() if l.strip()]),
                'wer': wer, 'cer': cer, 'text': text_on,
            }
            print(f"     ✓ Completed in {time_on:.2f}s | Chars: {len(text_on)}")

    # --- PRINT SUMMARY TABLE ---
    print("\n" + "="*80)
    print(" OCR BENCHMARK SUMMARY")
    print("="*80)
    
    if ref_text:
        print(f" {'Engine':<25} | {'Time':<8} | {'Chars':<7} | {'Lines':<7} | {'WER':<8} | {'CER':<8}")
        print(f" {'-'*25}-+-{'-'*8}-+-{'-'*7}-+-{'-'*7}-+-{'-'*8}-+-{'-'*8}")
        for key, res in results.items():
            wer_str = f"{res['wer']:.2%}" if res['wer'] is not None else "N/A"
            cer_str = f"{res['cer']:.2%}" if res['cer'] is not None else "N/A"
            print(f" {res['name']:<25} | {res['time']:<7.2f}s | {res['chars']:<7} | {res['lines']:<7} | {wer_str:<8} | {cer_str:<8}")
    else:
        print(f" {'Engine':<25} | {'Time':<8} | {'Chars':<7} | {'Lines':<7}")
        print(f" {'-'*25}-+-{'-'*8}-+-{'-'*7}-+-{'-'*7}")
        for key, res in results.items():
            print(f" {res['name']:<25} | {res['time']:<7.2f}s | {res['chars']:<7} | {res['lines']:<7}")
            
    print("="*80)

    # Save details to benchmark_log.txt for validation
    with open("benchmark_results.txt", "w", encoding='utf-8') as f:
        f.write("=== OCR BENCHMARK RESULTS ===\n\n")
        for key, res in results.items():
            f.write(f"--- {res['name']} ---\n")
            f.write(f"Time: {res['time']:.2f}s | Chars: {res['chars']} | Lines: {res['lines']}\n")
            if res['wer'] is not None:
                f.write(f"WER: {res['wer']:.2%} | CER: {res['cer']:.2%}\n")
            f.write("Text Extract:\n")
            f.write(res['text'])
            f.write("\n\n" + "="*50 + "\n\n")
            
    print("\n💾 Full texts saved to: benchmark_results.txt\n")


if __name__ == '__main__':
    main()
