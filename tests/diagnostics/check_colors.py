from PIL import Image
import numpy as np

img = Image.open('images/ApprovaSuodham.png')
img_gray = np.array(img.convert('L'))
h, w = img_gray.shape

print(f"Image shape: {w}x{h}")
print(f"Top-Left pixel (0,0): {img_gray[0,0]}")
print(f"Top-Right pixel (0, w-1): {img_gray[0, w-1]}")
print(f"Bottom-Left pixel (h-1, 0): {img_gray[h-1, 0]}")
print(f"Bottom-Right pixel (h-1, w-1): {img_gray[h-1, w-1]}")
print(f"Center pixel (h//2, w//2): {img_gray[h//2, w//2]}")
print(f"Mean value of whole image: {np.mean(img_gray):.1f}")
print(f"Min/Max value: {np.min(img_gray)} / {np.max(img_gray)}")

# Print a 10x10 slice around center
print("\nCenter 10x10 slice:")
print(img_gray[h//2-5:h//2+5, w//2-5:w//2+5])
