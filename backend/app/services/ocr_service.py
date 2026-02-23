from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OCRWord:
    text: str
    line_no: int
    confidence: float
    bbox: tuple[int, int, int, int]


@dataclass(slots=True)
class OCRBlock:
    block_no: int
    line_no: int
    text: str
    bbox: tuple[int, int, int, int]


@dataclass(slots=True)
class OCRResult:
    words: list[OCRWord]
    blocks: list[OCRBlock]
    avg_confidence: float


def run_ocr(image_bytes: bytes) -> OCRResult:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    words: list[OCRWord] = []
    blocks_map: dict[tuple[int, int], OCRBlock] = {}
    confidences: list[float] = []

    n = len(data.get("text", []))
    for idx in range(n):
        token = (data["text"][idx] or "").strip()
        if not token:
            continue

        conf = float(data.get("conf", ["0"] * n)[idx] or 0)
        line_no = int(data.get("line_num", ["1"] * n)[idx] or 1)
        block_no = int(data.get("block_num", ["1"] * n)[idx] or 1)
        left = int(data.get("left", ["0"] * n)[idx] or 0)
        top = int(data.get("top", ["0"] * n)[idx] or 0)
        width = int(data.get("width", ["0"] * n)[idx] or 0)
        height = int(data.get("height", ["0"] * n)[idx] or 0)
        bbox = (left, top, width, height)

        words.append(OCRWord(text=token, line_no=line_no, confidence=max(0.0, conf), bbox=bbox))
        if conf >= 0:
            confidences.append(conf)

        key = (block_no, line_no)
        block = blocks_map.get(key)
        if block is None:
            blocks_map[key] = OCRBlock(
                block_no=block_no,
                line_no=line_no,
                text=token,
                bbox=bbox,
            )
        else:
            x = min(block.bbox[0], left)
            y = min(block.bbox[1], top)
            w = max(block.bbox[0] + block.bbox[2], left + width) - x
            h = max(block.bbox[1] + block.bbox[3], top + height) - y
            block.text = f"{block.text} {token}"
            block.bbox = (x, y, w, h)

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    blocks = list(blocks_map.values())
    logger.info("OCR extracted %s words and %s blocks", len(words), len(blocks))
    return OCRResult(words=words, blocks=blocks, avg_confidence=avg_conf)
