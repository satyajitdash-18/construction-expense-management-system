"""OCR service with Tesseract integration and image preprocessing."""

import io
from typing import BinaryIO

import pytesseract
from PIL import Image, ImageEnhance, ImageFilter

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Configure tesseract path if specified
if settings.TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD


class OCRService:
    """Service for OCR processing with preprocessing pipeline."""

    def __init__(self) -> None:
        self.lang = settings.TESSERACT_LANG or "eng+hin"
        self.config = settings.TESSERACT_CONFIG or "--psm 6 --oem 3"

    def preprocess_image(self, image: "Image.Image | np.ndarray") -> Image.Image:  # type: ignore[name-defined]
        """Apply preprocessing pipeline to improve OCR accuracy.

        Accepts either a PIL Image or a numpy ndarray (H×W×C uint8).
        """
        import numpy as np  # local import to avoid hard dep at module level
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image.astype("uint8"))

        # Convert to grayscale
        if image.mode != "L":
            image = image.convert("L")


        # Enhance contrast
        contrast_enhancer = ImageEnhance.Contrast(image)
        image = contrast_enhancer.enhance(1.5)

        # Enhance sharpness
        sharpness_enhancer = ImageEnhance.Sharpness(image)
        image = sharpness_enhancer.enhance(2.0)

        # Denoise using median filter
        image = image.filter(ImageFilter.MedianFilter(size=3))

        # Auto-threshold (binarize)
        image = image.point(lambda x: 0 if x < 128 else 255, "1")

        # Deskew if needed
        image = self._deskew(image)

        # Morphological operations to clean up
        image = image.filter(ImageFilter.MaxFilter(size=3))
        image = image.filter(ImageFilter.MinFilter(size=3))

        return image

    def _deskew(self, image: Image.Image) -> Image.Image:
        """Deskew image using projection profile method."""
        try:
            # Convert to numpy for processing
            import numpy as np
            arr = np.array(image)

            # Find non-zero pixels
            coords = np.column_stack(np.where(arr > 0))
            if len(coords) < 100:
                return image

            # Calculate angle using minimum area rectangle
            from cv2 import minAreaRect

            rect = minAreaRect(coords)
            angle = rect[-1]

            # Correct angle
            if angle < -45:
                angle = 90 + angle

            # Only rotate if angle is significant
            if abs(angle) > 0.5:
                # Rotate using PIL
                image = image.rotate(-angle, expand=True, fillcolor=255)
                logger.debug("Deskewed image", angle=angle)
        except Exception as e:
            logger.warning("Deskew failed, skipping", error=str(e))

        return image

    def extract_text(self, image: Image.Image) -> dict:
        """Extract text and metadata from preprocessed image."""
        # Preprocess
        processed = self.preprocess_image(image)

        # Extract text with confidence data
        data = pytesseract.image_to_data(
            processed,
            lang=self.lang,
            config=self.config,
            output_type=pytesseract.Output.DICT,
        )

        # Extract full text
        text = pytesseract.image_to_string(
            processed,
            lang=self.lang,
            config=self.config,
        )

        # Calculate average confidence
        confidences = [int(c) for c in data["conf"] if int(c) > 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        # Get bounding boxes for lines
        lines = []
        for i in range(len(data["text"])):
            if int(data["conf"][i]) > 0 and data["text"][i].strip():
                lines.append({
                    "text": data["text"][i],
                    "confidence": int(data["conf"][i]),
                    "bbox": {
                        "x": int(data["left"][i]),
                        "y": int(data["top"][i]),
                        "w": int(data["width"][i]),
                        "h": int(data["height"][i]),
                    },
                    "line_num": int(data["line_num"][i]),
                    "block_num": int(data["block_num"][i]),
                })

        return {
            "full_text": text.strip(),
            "avg_confidence": avg_confidence,
            "lines": lines,
            "word_count": len([c for c in confidences if c > 0]),
        }

    def process_file(self, file_data: bytes) -> dict:
        """Process image file from bytes."""
        image = Image.open(io.BytesIO(file_data))
        return self.extract_text(image)

    def process_fileobj(self, fileobj: BinaryIO) -> dict:
        """Process image from file-like object."""
        fileobj.seek(0)
        image = Image.open(fileobj)
        return self.extract_text(image)


def create_ocr_service() -> OCRService:
    """Factory for creating OCRService."""
    return OCRService()
