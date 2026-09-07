#!/usr/bin/env python3
"""
Test script for multithreading performance comparison
"""
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from pdf_to_epub_converter_optimized_v2 import OptimizedPDFToEPUBConverter


def test_conversion(pdf_path, enable_parallel=True, batch_size=None, max_pages=10):
    """Test conversion with specified settings"""
    
    mode = "PARALLEL" if enable_parallel else "SEQUENTIAL"
    batch_info = f" (batch_size={batch_size})" if batch_size else " (auto batch)"
    
    print(f"\n{'='*70}")
    print(f"Testing {mode} mode{batch_info if enable_parallel else ''}")
    print(f"{'='*70}\n")
    
    output_path = Path(f"test_output_{mode.lower()}.epub")
    
    # Create converter
    converter = OptimizedPDFToEPUBConverter(
        language='tel+eng',
        dpi=250,
        detect_tables=True,
        preserve_images=True,
        max_workers=4,
        enable_parallel=enable_parallel,
        batch_size=batch_size
    )
    
    # Time the conversion
    start_time = time.time()
    
    success = converter.convert_streaming(
        Path(pdf_path),
        output_path,
        title=f"Test {mode}",
        author="Test",
        max_pages=max_pages
    )
    
    elapsed = time.time() - start_time
    
    print(f"\n{'='*70}")
    print(f"Results for {mode} mode:")
    print(f"  Success: {success}")
    print(f"  Time: {elapsed:.1f}s ({elapsed/60:.2f} min)")
    print(f"  Average: {elapsed/max_pages:.2f}s per page")
    print(f"  Output: {output_path}")
    print(f"{'='*70}\n")
    
    return elapsed


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_multithreading.py <pdf_file> [max_pages]")
        print("Example: python test_multithreading.py sample.pdf 10")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    
    if not Path(pdf_path).exists():
        print(f"Error: PDF file not found: {pdf_path}")
        sys.exit(1)
    
    print(f"\n{'#'*70}")
    print(f"# Multithreading Performance Test")
    print(f"# PDF: {pdf_path}")
    print(f"# Max pages: {max_pages}")
    print(f"{'#'*70}")
    
    # Test 1: Sequential processing
    time_sequential = test_conversion(pdf_path, enable_parallel=False, max_pages=max_pages)
    
    # Test 2: Parallel processing (auto batch size)
    time_parallel_auto = test_conversion(pdf_path, enable_parallel=True, batch_size=None, max_pages=max_pages)
    
    # Test 3: Parallel processing (batch size = 4)
    time_parallel_4 = test_conversion(pdf_path, enable_parallel=True, batch_size=4, max_pages=max_pages)
    
    # Summary
    print(f"\n{'='*70}")
    print(f"PERFORMANCE SUMMARY")
    print(f"{'='*70}")
    print(f"Sequential:          {time_sequential:.1f}s ({time_sequential/max_pages:.2f}s/page)")
    print(f"Parallel (auto):     {time_parallel_auto:.1f}s ({time_parallel_auto/max_pages:.2f}s/page)")
    print(f"Parallel (batch=4):  {time_parallel_4:.1f}s ({time_parallel_4/max_pages:.2f}s/page)")
    print(f"\nSpeedup (auto):      {time_sequential/time_parallel_auto:.2f}x")
    print(f"Speedup (batch=4):   {time_sequential/time_parallel_4:.2f}x")
    print(f"{'='*70}\n")


if __name__ == '__main__':
    main()
