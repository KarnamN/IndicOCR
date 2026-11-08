#!/usr/bin/env bash
# Verbose Surya OCR install into the shared WSL venv, with clear step markers
# so failures are easy to spot in the log. Every command's real output is
# shown (no output silenced/truncated) since pip's own progress bar and any
# error text both need to reach the log file.

set -uo pipefail

step() { echo; echo "==== $1 ===="; }

step "1/6 Checking WSL venv exists"
VENV=~/venvs/ocr-common
if [ ! -f "$VENV/bin/activate" ]; then
    echo "ERROR: venv not found at $VENV"
    exit 1
fi
echo "OK: $VENV"

step "2/6 Activating venv"
source "$VENV/bin/activate"
echo "python: $(which python3)"
python3 --version

step "3/6 Current torch / surya state (before install)"
python3 -c "import torch; print('torch:', torch.__version__, 'cuda available:', torch.cuda.is_available())" 2>&1 || echo "torch not installed yet"
pip show surya-ocr 2>&1 | head -5 || true

step "4/6 Disk space check (models + torch can be several GB)"
df -h "$HOME" 2>&1

step "5/6 Installing surya-ocr (verbose pip output)"
pip install -v surya-ocr
PIP_EXIT=$?
echo "pip install exit code: $PIP_EXIT"

step "6/6 Post-install verification"
python3 -c "
import surya
print('surya module path:', surya.__file__)
try:
    import surya.recognition
    print('surya.recognition import OK')
except Exception as e:
    print('surya.recognition import FAILED:', e)
try:
    import surya.detection
    print('surya.detection import OK')
except Exception as e:
    print('surya.detection import FAILED:', e)
"
VERIFY_EXIT=$?

echo
if [ "$PIP_EXIT" -eq 0 ] && [ "$VERIFY_EXIT" -eq 0 ]; then
    echo "RESULT: SUCCESS"
else
    echo "RESULT: FAILED (pip_exit=$PIP_EXIT verify_exit=$VERIFY_EXIT)"
fi
