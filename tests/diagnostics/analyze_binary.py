import sys
import os
from pathlib import Path
from PIL import Image
import numpy as np
import cv2

# Add src to path
sys.path.append('src')

img_path = Path('images/ApprovaSuodham.png')
if img_path.exists():
    image = Image.open(img_path).convert('RGB')
    w, h = image.size
    
    img_gray = np.array(image.convert('L'))
    _, binary = cv2.threshold(img_gray, 127, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    
    # Check overall stats of binary image
    total_pixels = binary.size
    white_pixels = np.sum(binary == 255)
    print(f"Original image size: {w}x{h}")
    print(f"Binary image: {white_pixels} white pixels ({white_pixels/total_pixels*100:.1f}%), {total_pixels - white_pixels} black pixels")
    
    # Save the original binary image to see what it looks like
    cv2.imwrite('scratch/binary_raw.png', binary)
    print("Saved raw binary image to scratch/binary_raw.png")
    
    # Let's see the projection profile across the page in steps of 50px
    v_proj = np.sum(binary, axis=0) / 255
    print("\nVertical projection (average white pixels per column in 50px bands):")
    for i in range(0, w, 50):
        end = min(i + 50, w)
        avg_val = np.mean(v_proj[i:end])
        print(f"  Col {i:4d} to {end:4d}: {avg_val:.1f} rows")
        
else:
    print("Image not found")
