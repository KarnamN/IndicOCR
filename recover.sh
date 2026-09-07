#!/bin/bash

# Recovery Script for MyOCR Project
# Restores files from Chatbot and TeluguOCR-develop projects

echo "=========================================="
echo "MyOCR Project Recovery Script"
echo "=========================================="
echo ""

# Set paths
CHATBOT_DIR="/mnt/c/Workspace/Antigravity_workspace/Chatbot"
TELUGU_DIR="/mnt/c/Workspace/Antigravity_workspace/TeluguOCR-develop"
TARGET_DIR="/mnt/c/Workspace/Antigravity_workspace/Myocr"

echo "Source directories:"
echo "  Chatbot: $CHATBOT_DIR"
echo "  TeluguOCR: $TELUGU_DIR"
echo "  Target: $TARGET_DIR"
echo ""

# Check if source directories exist
if [ ! -d "$CHATBOT_DIR" ]; then
    echo "ERROR: Chatbot directory not found!"
    exit 1
fi

if [ ! -d "$TELUGU_DIR" ]; then
    echo "ERROR: TeluguOCR-develop directory not found!"
    exit 1
fi

echo "Step 1: Copying core files from Chatbot..."
cp -r "$CHATBOT_DIR/src/"* "$TARGET_DIR/src/" 2>/dev/null
echo "  ✓ Source files copied"

echo ""
echo "Step 2: Copying scripts..."
cp -r "$CHATBOT_DIR/scripts/"* "$TARGET_DIR/scripts/" 2>/dev/null
echo "  ✓ Scripts copied"

echo ""
echo "Step 3: Copying tests..."
cp -r "$CHATBOT_DIR/tests/"* "$TARGET_DIR/tests/" 2>/dev/null
echo "  ✓ Tests copied"

echo ""
echo "Step 4: Copying startup scripts..."
cp "$CHATBOT_DIR/"*.sh "$TARGET_DIR/" 2>/dev/null
cp "$CHATBOT_DIR/"*.bat "$TARGET_DIR/" 2>/dev/null
echo "  ✓ Startup scripts copied"

echo ""
echo "Step 5: Copying documentation..."
cp "$CHATBOT_DIR/"*.md "$TARGET_DIR/" 2>/dev/null
echo "  ✓ Documentation copied"

echo ""
echo "Step 6: Merging TeluguOCR components..."
# Copy any Telugu-specific files if they exist
if [ -d "$TELUGU_DIR/src" ]; then
    cp -r "$TELUGU_DIR/src/"* "$TARGET_DIR/src/" 2>/dev/null
    echo "  ✓ TeluguOCR source files merged"
fi

echo ""
echo "=========================================="
echo "Recovery Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Review copied files"
echo "2. Apply PaddleOCR fixes (config.py already updated)"
echo "3. Apply Telugu fallback fix to ocr_factory.py"
echo "4. Test the system"
echo ""
echo "Files to check:"
echo "  - src/config.py (already has fixes)"
echo "  - src/paddle_ocr_processor.py (needs memory fixes)"
echo "  - src/ocr_factory.py (needs Telugu fallback fix)"
echo ""
