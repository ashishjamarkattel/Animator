"""CRAFT (Character Region Awareness for Text) detection via ONNX Runtime.

No PyTorch dependency needed. The model is lazy-loaded on first use.

The bundled model (models/craft.onnx) is an ONNX export of craft_mlt_25k
from https://github.com/clovaai/CRAFT-pytorch. Set CRAFT_MODEL_PATH to use a
different file.
"""

import os
from pathlib import Path

import cv2
import numpy as np

CRAFT_MODEL_PATH = os.environ.get(
    "CRAFT_MODEL_PATH", str(Path(__file__).parent / "models" / "craft.onnx")
)

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class CRAFTDetector:
    """Lazy-loaded CRAFT text detector running via ONNX Runtime."""

    def __init__(self, model_path: str = CRAFT_MODEL_PATH, text_threshold: float = 0.4,
                 link_threshold: float = 0.3, low_text: float = 0.25,
                 long_side: int = 640):
        self.model_path = model_path
        self.text_threshold = text_threshold
        self.link_threshold = link_threshold
        self.low_text = low_text
        self.long_side = long_side
        self._session = None

    def load(self):
        if self._session is not None:
            return
        try:
            import onnxruntime as ort
        except ImportError:
            raise ImportError("onnxruntime is required for CRAFT: pip install onnxruntime")
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                f"CRAFT ONNX model not found at {self.model_path}. "
                f"Set CRAFT_MODEL_PATH env var or place the model there."
            )
        self._session = ort.InferenceSession(
            self.model_path,
            providers=["CPUExecutionProvider"],
        )

    def preprocess(self, img: np.ndarray) -> tuple[np.ndarray, float]:
        h, w = img.shape[:2]
        scale = self.long_side / max(h, w)
        new_h, new_w = int(h * scale), int(w * scale)
        new_h = max(32, (new_h // 32) * 32)
        new_w = max(32, (new_w // 32) * 32)

        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        x = resized.astype(np.float32) / 255.0
        x = (x - _MEAN) / _STD
        x = x.transpose(2, 0, 1)[np.newaxis]
        return x, (h / new_h, w / new_w)

    def detect(self, img: np.ndarray) -> np.ndarray:
        self.load()
        h, w = img.shape[:2]

        blob, (ratio_h, ratio_w) = self.preprocess(img)

        input_name = self._session.get_inputs()[0].name
        output_names = [o.name for o in self._session.get_outputs()]
        outputs = self._session.run(output_names, {input_name: blob})

        region_score = None
        affinity_score = None

        for out in outputs:
            s = out.squeeze()
            if s.ndim == 3 and s.shape[-1] == 2:
                region_score = s[:, :, 0]
                affinity_score = s[:, :, 1]
                break
            elif s.ndim == 3 and s.shape[0] == 2:
                region_score = s[0]
                affinity_score = s[1]
                break
            elif s.ndim == 2 and region_score is None:
                region_score = s

        if region_score is None:
            region_score = outputs[0].squeeze()
            if region_score.ndim == 3:
                region_score = region_score[:, :, 0] if region_score.shape[-1] == 2 else region_score[0]

        text_score = region_score.copy()
        if affinity_score is not None:
            text_score = np.maximum(text_score, affinity_score * 0.7)

        binary = (text_score > self.low_text).astype(np.uint8)
        kern = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kern, iterations=1)

        text_mask = cv2.resize(binary, (w, h), interpolation=cv2.INTER_NEAREST)
        return text_mask.astype(bool)
