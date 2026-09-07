#!/bin/bash

echo "========================================"
echo "PDF to EPUB Converter - Clean Restart"
echo "========================================"
echo ""

echo "Clearing Python cache..."
find src -type f -name "*.pyc" -delete 2>/dev/null
find src -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
echo "✓ Cache cleared."
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "Error: Failed to create virtual environment"
        echo "Please ensure Python 3 is installed and in PATH"
        read -p "Press Enter to exit..."
        exit 1
    fi
    echo "Virtual environment created successfully"
    echo ""
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "Error: Failed to activate virtual environment"
    read -p "Press Enter to exit..."
    exit 1
fi

echo ""
echo "Starting server on http://localhost:5001"
echo "Press Ctrl+C to stop"
echo ""

# Ensure project root is on PYTHONPATH
export PYTHONPATH=$(pwd):$PYTHONPATH

# Start the Flask application
python3 src/app.py

read -p "Press Enter to exit..."
