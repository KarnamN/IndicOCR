import cv2
import numpy as np
from PIL import Image
import os

def debug_analyzer(image_path):
    img = Image.open(image_path).convert('L')
    img_gray = np.array(img)
    h, w = img_gray.shape
    
    _, binary = cv2.threshold(img_gray, 127, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    
    # Horizontal lines
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    detect_horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
    h_lines = np.sum(detect_horizontal > 0)
    
    # Vertical lines
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
    detect_vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
    v_lines = np.sum(detect_vertical > 0)
    
    # Rectangles/Boxes
    contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    rect_count = 0
    for cnt in contours:
        approx = cv2.approxPolyDP(cnt, 0.02 * cv2.arcLength(cnt, True), True)
        if len(approx) == 4:
            x,y,bw,bh = cv2.boundingRect(cnt)
            if bw > 20 and bh > 20: # Only count boxes larger than 20x20
                rect_count += 1
                
    print(f"Image Resolution: {w}x{h}")
    print(f"Horizontal Line Pixels: {h_lines}")
    print(f"Vertical Line Pixels: {v_lines}")
    print(f"Significant Rectangles Count: {rect_count}")
    print(f"Current conditions: has_table={h_lines > 1000 and v_lines > 1000}, has_many_boxes={rect_count > 10}")

if __name__ == "__main__":
    # Test on the uploaded image
    img_path = "/home/naveen/.gemini/antigravity/brain/a833ce51-4694-444f-9c27-bf5c41851fa4/uploaded_image_1768921721739.png"
    if os.path.exists(img_path):
        debug_analyzer(img_path)
    else:
        print("Image for testing not found.")
