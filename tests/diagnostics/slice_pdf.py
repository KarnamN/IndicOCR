import fitz
import sys

try:
    src = fitz.open("data/uploads/20260606_143544_2f0f09c0_pdf")
    doc = fitz.open()
    # Copy pages 3, 4, 5 (0-indexed: 2, 3, 4)
    doc.insert_pdf(src, from_page=2, to_page=4)
    doc.save("data/uploads/small_test.pdf")
    doc.close()
    src.close()
    print("SUCCESS: sliced PDF saved to data/uploads/small_test.pdf")
except Exception as e:
    print(f"Error slicing PDF: {e}")
    sys.exit(1)
