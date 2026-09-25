#!/usr/bin/env bash
set -euo pipefail

COMMON_VENV="${COMMON_VENV:-$HOME/venvs/ocr-common}"
INDIC_VENV="${INDIC_VENV:-$HOME/indicphotoocr-venv}"
INDIC_REPO="${INDIC_REPO:-$HOME/IndicPhotoOCR}"
MYOCR_VENV="${MYOCR_VENV:-/mnt/c/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026/venv}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

if [[ ! -x "$MYOCR_VENV/bin/python" ]]; then
    echo "Missing MyOCR environment: $MYOCR_VENV" >&2
    exit 1
fi
if [[ ! -x "$INDIC_VENV/bin/python" ]]; then
    echo "Missing IndicPhotoOCR environment: $INDIC_VENV" >&2
    exit 1
fi
if [[ ! -d "$INDIC_REPO" ]]; then
    echo "Missing IndicPhotoOCR repository: $INDIC_REPO" >&2
    exit 1
fi

mkdir -p "$(dirname "$COMMON_VENV")"
if [[ ! -x "$COMMON_VENV/bin/python" ]]; then
    python3 -m venv "$COMMON_VENV"
fi

COMMON_PIP="$COMMON_VENV/bin/python -m pip"
$COMMON_PIP install --upgrade pip

"$MYOCR_VENV/bin/python" -m pip freeze > "$WORK_DIR/myocr.txt"
"$INDIC_VENV/bin/python" -m pip freeze > "$WORK_DIR/indic.txt"

# Install each inventory separately. The second inventory resolves duplicate
# package pins instead of asking pip to satisfy incompatible exact versions at once.
for inventory in "$WORK_DIR/myocr.txt" "$WORK_DIR/indic.txt"; do
    grep -vE '^(torch|torchvision|torchaudio|nvidia-|triton|paddlepaddle|paddleocr|IndicPhotoOCR|ultra[-_]infer[-_]python)([ =<>!~]|$)' "$inventory" \
        | grep -vE '^-e |^file:' > "$inventory.filtered"
    $COMMON_PIP install -r "$inventory.filtered"
done

$COMMON_PIP install paddlepaddle paddleocr
$COMMON_PIP install -e "$INDIC_REPO" --no-deps
grep -vE 'ultra[-_]infer[-_]python|ultra_infer_python[[:space:]]*@' "$PROJECT_ROOT/requirements.txt" \
    > "$WORK_DIR/project-requirements.txt"
$COMMON_PIP install -r "$WORK_DIR/project-requirements.txt"

# Some merged requirements can pull the default CUDA Torch wheel. Remove it
# after all other installs, then install the CPU-only pair last.
$COMMON_PIP uninstall -y torch torchvision torchaudio nvidia-cublas-cu12 nvidia-cuda-cupti-cu12 \
    nvidia-cuda-nvrtc-cu12 nvidia-cuda-runtime-cu12 nvidia-cudnn-cu12 nvidia-cufft-cu12 \
    nvidia-curand-cu12 nvidia-cusolver-cu12 nvidia-cusparse-cu12 nvidia-nccl-cu12 \
    nvidia-nvjitlink-cu12 nvidia-nvtx-cu12 triton >/dev/null 2>&1 || true
$COMMON_PIP install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0 torchvision==0.21.0

$COMMON_PIP freeze > "$COMMON_VENV/requirements.lock.txt"
cat > "$COMMON_VENV/README.txt" <<EOF
Shared OCR environment
Python: $COMMON_VENV/bin/python
Use: source $COMMON_VENV/bin/activate
Lock: $COMMON_VENV/requirements.lock.txt
EOF

echo "Shared environment ready: $COMMON_VENV"
echo "Python: $COMMON_VENV/bin/python"
$COMMON_VENV/bin/python - <<'PY'
import torch
print(f"torch={torch.__version__}")
print(f"cuda_available={torch.cuda.is_available()}")
import paddleocr
print(f"paddleocr={getattr(paddleocr, '__version__', 'installed')}")
from IndicPhotoOCR.ocr import OCR
print("indicphotoocr=ok")
import pytesseract
print(f"tesseract={pytesseract.get_tesseract_version().splitlines()[0]}")
PY
