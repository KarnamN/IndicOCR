#!/bin/bash
#
# Test script: Process first 10 pages of a PDF to validate performance
#
# Usage: ./scripts/test_10_pages.sh input.pdf

set -e  # Exit on error

echo "========================================="
echo "10-Page Test - Optimized Converter"
echo "========================================="
echo ""

# Check arguments
if [ $# -lt 1 ]; then
    echo "Usage: $0 <input.pdf> [output.epub]"
    echo ""
    echo "Example:"
    echo "  $0 large_book.pdf test_output.epub"
    exit 1
fi

INPUT_PDF="$1"
OUTPUT_EPUB="${2:-outputs/test_10_pages.epub}"

# Check if input exists
if [ ! -f "$INPUT_PDF" ]; then
    echo "Error: Input file not found: $INPUT_PDF"
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Create outputs directory
mkdir -p outputs

# Run optimized converter on first 10 pages
echo ""
echo "Processing first 10 pages..."
echo "Input:  $INPUT_PDF"
echo "Output: $OUTPUT_EPUB"
echo ""

python3 src/pdf_to_epub_converter_optimized_v2.py \
    "$INPUT_PDF" \
    "$OUTPUT_EPUB" \
    --max-pages 10 \
    --skip-first-pages 2 \
    --no-tables \
    --dpi 250 \
    --workers 4 \
    --language "tel+eng"

EXIT_CODE=$?

echo ""
echo "========================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo "✓ Test completed successfully!"
    echo "✓ Output saved to: $OUTPUT_EPUB"
    echo ""
    echo "Next steps:"
    echo "  1. Open $OUTPUT_EPUB in an e-reader to verify quality"
    echo "  2. If quality is good, process full book:"
    echo "     python3 src/pdf_to_epub_converter_optimized_v2.py \\"
    echo "       $INPUT_PDF outputs/full_book.epub"
else
    echo "✗ Test failed with exit code: $EXIT_CODE"
    echo "Check the logs above for errors"
fi
echo "========================================="

exit $EXIT_CODE
