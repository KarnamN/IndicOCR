import sys
from paddle_v5_processor import PaddleV5Processor
from PIL import Image
p = PaddleV5Processor()
img = Image.new('RGB', (100, 30), color = 'white')
res = p.extract_text(img)
print(res)
