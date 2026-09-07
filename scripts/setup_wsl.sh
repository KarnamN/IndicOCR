#!/bin/bash
# Quick setup script for WSL Ubuntu

echo "=========================================="
echo "  PDF to EPUB Converter - WSL Setup"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running in WSL
if ! grep -qi microsoft /proc/version; then
    echo -e "${YELLOW}Warning: This doesn't appear to be WSL${NC}"
    echo "This script is designed for WSL Ubuntu"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo -e "${GREEN}Step 1: Updating system packages...${NC}"
sudo apt update

echo ""
echo -e "${GREEN}Step 2: Installing system dependencies...${NC}"
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    tesseract-ocr \
    tesseract-ocr-tel \
    poppler-utils \
    libgl1-mesa-glx \
    libglib2.0-0

# Check if installations succeeded
if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to install system dependencies${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Step 3: Verifying Tesseract installation...${NC}"
tesseract --version
echo ""
echo "Available languages:"
tesseract --list-langs

echo ""
echo -e "${GREEN}Step 4: Creating virtual environment...${NC}"
if [ -d "venv" ]; then
    echo -e "${YELLOW}Virtual environment already exists. Skipping...${NC}"
else
    python3 -m venv venv
    echo "Virtual environment created"
fi

echo ""
echo -e "${GREEN}Step 5: Activating virtual environment...${NC}"
source venv/bin/activate

echo ""
echo -e "${GREEN}Step 6: Upgrading pip...${NC}"
pip install --upgrade pip

echo ""
echo -e "${GREEN}Step 7: Installing Python dependencies...${NC}"
echo "This may take a few minutes..."
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to install Python dependencies${NC}"
    echo "Trying to install packages individually..."
    
    pip install Flask==3.0.0 Werkzeug==3.0.1
    pip install flask-socketio==5.3.5 python-socketio==5.10.0
    pip install pymupdf==1.23.8
    pip install pdf2image==1.16.3
    pip install pytesseract==0.3.10
    pip install Pillow==10.1.0
    pip install opencv-python==4.8.1.78
    pip install numpy==1.26.2
    pip install pandas==2.1.4
    pip install openpyxl==3.1.2
    pip install ebooklib==0.18
fi

echo ""
echo -e "${GREEN}Step 8: Testing installation...${NC}"
python test_installation.py

echo ""
echo "=========================================="
echo -e "${GREEN}  Setup Complete!${NC}"
echo "=========================================="
echo ""
echo "To activate the virtual environment in future sessions:"
echo "  source venv/bin/activate"
echo ""
echo "To run the web application:"
echo "  python app.py"
echo ""
echo "To convert a large PDF:"
echo "  python convert_large_pdf.py input.pdf output.epub"
echo ""
echo "For your 450-page PDF, use:"
echo "  python convert_large_pdf.py your_450_page.pdf output.epub --chunk-size 5 --workers 1 --dpi 150"
echo ""
echo "=========================================="
