"""Prototype: can TextBPN's FPN+seg_head backbone export to ONNX and run faster
under ONNXRuntime/OpenVINO than native PyTorch? Standalone, no production wiring.

Only exports the CNN portion (self.fpn + self.seg_head) -- the boundary-proposal
step (self.BPN) stays native PyTorch, see the investigation notes for why.
"""
import sys
import time

sys.path.insert(0, "src")
import torch
import torch.nn as nn

import config_v5 as active_config
sys.modules["config"] = active_config
from indicphoto_ocr_processor import IndicPhotoOCRProcessor

print("Loading IndicPhotoOCR detector...")
proc = IndicPhotoOCRProcessor(device="cpu", identifier_lang="telugu", identifier_mode="hinted")
detector = proc.engine.detector
model = detector.model
model.eval()


class Backbone(nn.Module):
    """Exactly textnet.py's TextNet.forward() up to cnn_feats/fy_preds, no more."""
    def __init__(self, m):
        super().__init__()
        self.fpn = m.fpn
        self.seg_head = m.seg_head
        from IndicPhotoOCR.detection.textbpn.cfglib.config import config as cfg
        self.scale = cfg.scale

    def forward(self, image):
        b, c, h, w = image.shape
        up1, _, _, _, _ = self.fpn(image)
        up1 = up1[:, :, :h // self.scale, :w // self.scale]
        preds = self.seg_head(up1)
        fy_preds = torch.cat([torch.sigmoid(preds[:, 0:2, :, :]), preds[:, 2:4, :, :]], dim=1)
        cnn_feats = torch.cat([up1, fy_preds], dim=1)
        return cnn_feats, fy_preds


backbone = Backbone(model)
backbone.eval()

# Representative size: detect() pads to a square canvas sized to the longer side,
# rounded up to a stride-32 multiple. A 1500px-capped page is typically ~1500-1536.
SIZE = 1536
dummy = torch.randn(1, 3, SIZE, SIZE)

print(f"\n--- Native PyTorch timing (size={SIZE}) ---")
with torch.no_grad():
    for _ in range(2):
        backbone(dummy)  # warmup
    t0 = time.perf_counter()
    for _ in range(3):
        out_pt = backbone(dummy)
    t_pt = (time.perf_counter() - t0) / 3
print(f"PyTorch: {t_pt:.2f}s/call  (cnn_feats shape={out_pt[0].shape}, fy_preds shape={out_pt[1].shape})")

print("\n--- Attempting ONNX export ---")
onnx_path = "/tmp/textbpn_backbone.onnx"
try:
    torch.onnx.export(
        backbone, dummy, onnx_path,
        input_names=["image"], output_names=["cnn_feats", "fy_preds"],
        dynamic_axes={"image": {2: "h", 3: "w"}, "cnn_feats": {2: "h", 3: "w"}, "fy_preds": {2: "h", 3: "w"}},
        opset_version=17,
    )
    print(f"Export OK -> {onnx_path}")
except Exception as exc:
    print(f"EXPORT FAILED: {type(exc).__name__}: {exc}")
    sys.exit(1)

print("\n--- ONNXRuntime timing ---")
import onnxruntime as ort
sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
np_dummy = dummy.numpy()
for _ in range(2):
    sess.run(None, {"image": np_dummy})
t0 = time.perf_counter()
for _ in range(3):
    out_ort = sess.run(None, {"image": np_dummy})
t_ort = (time.perf_counter() - t0) / 3
print(f"ONNXRuntime: {t_ort:.2f}s/call")

print("\n--- Correctness check (PyTorch vs ONNXRuntime) ---")
import numpy as np
diff_cnn = np.abs(out_pt[0].numpy() - out_ort[0]).max()
diff_fy = np.abs(out_pt[1].numpy() - out_ort[1]).max()
print(f"max abs diff cnn_feats={diff_cnn:.6f}  fy_preds={diff_fy:.6f}")

print("\n--- Different input size (tests the dynamic-shape concern) ---")
SIZE2 = 1024
dummy2 = torch.randn(1, 3, SIZE2, SIZE2)
with torch.no_grad():
    out_pt2 = backbone(dummy2)
out_ort2 = sess.run(None, {"image": dummy2.numpy()})
diff_cnn2 = np.abs(out_pt2[0].numpy() - out_ort2[0]).max()
print(f"size={SIZE2}: max abs diff cnn_feats={diff_cnn2:.6f} (shape pt={out_pt2[0].shape} ort={out_ort2[0].shape})")

print(f"\n=== SUMMARY ===")
print(f"PyTorch:     {t_pt:.2f}s/call")
print(f"ONNXRuntime: {t_ort:.2f}s/call")
print(f"Speedup:     {t_pt/t_ort:.1f}x")
