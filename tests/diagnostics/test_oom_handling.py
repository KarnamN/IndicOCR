import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from PIL import Image

# Add src to path
sys.path.append('src')

# Mocking modules that might fail on import due to dependencies
sys.modules['telugu_post_processor'] = MagicMock()
sys.modules['telugu_text_processor'] = MagicMock()

from qwen_ocr_processor import QwenOCRProcessor
from pdf_to_epub_converter_optimized_v2 import OptimizedPDFToEPUBConverter

class TestOCREscalation(unittest.TestCase):
    
    @patch('requests.post')
    def test_qwen_oom_raises_error(self, mock_post):
        # Setup mock response for OOM
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = '{"error":"model requires more system memory (10.1 GiB) than is available (7.2 GiB)"}'
        mock_post.return_value = mock_response
        
        processor = QwenOCRProcessor()
        with self.assertRaises(RuntimeError) as cm:
            processor.extract_text(Image.new('RGB', (100, 100)))
        
        self.assertIn("Qwen OOM", str(cm.exception))
        print("✅ Qwen OOM correctly raises RuntimeError")

    @patch('pdf_to_epub_converter_optimized_v2.OptimizedPDFToEPUBConverter._ocr_single_image')
    def test_escalation_ladder_flow(self, mock_ocr):
        # We'll test the logic inside the converter's _ocr_single_image by actually running it
        # but mocking the individual processors
        pass

if __name__ == '__main__':
    # Due to complex dependencies in the converter, we'll focus on the Qwen processor unit test first
    suite = unittest.TestLoader().loadTestsFromTestCase(TestOCREscalation)
    unittest.TextTestRunner().run(suite)
