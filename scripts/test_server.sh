#!/bin/bash

echo "=========================================="
echo "Testing Flask Server Startup"
echo "=========================================="
echo ""

cd /mnt/c/Workspace/Antigravity_workspace/Myocr

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Test imports
echo "Testing Python imports..."
python3 -c "
import sys
sys.path.insert(0, 'src')
try:
    import config
    print(f'✓ Config loaded: HOST={config.HOST}, PORT={config.PORT}')
    import flask
    print(f'✓ Flask version: {flask.__version__}')
    import flask_socketio
    print('✓ Flask-SocketIO available')
    print('')
    print('All imports successful!')
except Exception as e:
    print(f'✗ Import error: {e}')
    exit(1)
"

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "Starting Flask server..."
    echo "Server will be available at:"
    echo "  http://localhost:5001"
    echo "  http://127.0.0.1:5001"
    echo ""
    echo "Press Ctrl+C to stop"
    echo "=========================================="
    echo ""
    
    export PYTHONPATH=$(pwd):$PYTHONPATH
    python3 src/app.py
else
    echo "Failed to start server due to import errors"
    exit 1
fi
