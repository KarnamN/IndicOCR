#!/bin/bash
# Install tessdata_best for Telugu and English
# This script upgrades Tesseract traineddata to the latest best models

set -e  # Exit on error

echo "=========================================="
echo "Telugu Traineddata Upgrade Script"
echo "=========================================="
echo ""

# Check if files are downloaded
if [ ! -f "/tmp/tel.traineddata" ] || [ ! -f "/tmp/eng.traineddata" ]; then
    echo "Error: Traineddata files not found in /tmp/"
    echo "Please run the download commands first:"
    echo "  cd ../tmp"
    echo "  wget https://github.com/tesseract-ocr/tessdata_best/raw/main/tel.traineddata"
    echo "  wget https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata"
    exit 1
fi

echo "✓ Found downloaded traineddata files:"
ls -lh /tmp/tel.traineddata /tmp/eng.traineddata
echo ""

# Backup current files
echo "Creating backups of current traineddata..."
sudo cp /usr/share/tesseract-ocr/5/tessdata/tel.traineddata \
        /usr/share/tesseract-ocr/5/tessdata/tel.traineddata.backup
echo "✓ Backed up tel.traineddata"

sudo cp /usr/share/tesseract-ocr/5/tessdata/eng.traineddata \
        /usr/share/tesseract-ocr/5/tessdata/eng.traineddata.backup
echo "✓ Backed up eng.traineddata"
echo ""

# Install new files
echo "Installing new traineddata files..."
sudo mv /tmp/tel.traineddata /usr/share/tesseract-ocr/5/tessdata/tel.traineddata
echo "✓ Installed new tel.traineddata (tessdata_best)"

sudo mv /tmp/eng.traineddata /usr/share/tesseract-ocr/5/tessdata/eng.traineddata
echo "✓ Installed new eng.traineddata (tessdata_best)"
echo ""

# Verify installation
echo "Verifying installation..."
echo "New file sizes:"
ls -lh /usr/share/tesseract-ocr/5/tessdata/tel.traineddata
ls -lh /usr/share/tesseract-ocr/5/tessdata/eng.traineddata
echo ""

echo "Available languages:"
tesseract --list-langs
echo ""

echo "=========================================="
echo "✓ Installation Complete!"
echo "=========================================="
echo ""
echo "Changes:"
echo "  - Telugu: 2.7MB (2019) → 8.7MB (tessdata_best)"
echo "  - English: Updated to tessdata_best"
echo ""
echo "Expected improvements:"
echo "  - 7-12% better accuracy for Telugu"
echo "  - Better handling of complex characters"
echo "  - 20-30% slower processing (acceptable)"
echo ""
echo "Backups saved at:"
echo "  /usr/share/tesseract-ocr/5/tessdata/tel.traineddata.backup"
echo "  /usr/share/tesseract-ocr/5/tessdata/eng.traineddata.backup"
echo ""
echo "To rollback if needed:"
echo "  sudo cp /usr/share/tesseract-ocr/5/tessdata/tel.traineddata.backup \\"
echo "          /usr/share/tesseract-ocr/5/tessdata/tel.traineddata"
echo ""
