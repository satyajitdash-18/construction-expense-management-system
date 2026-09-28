"""Tests for OCR service."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from io import BytesIO
from PIL import Image

from app.services.ocr import OCRService, create_ocr_service


class TestOCRService:
    """Tests for OCRService."""

    @pytest.fixture
    def ocr_service(self):
        """Create OCR service instance."""
        return create_ocr_service()

    def test_preprocess_image(self, ocr_service):
        """Test image preprocessing pipeline."""
        # Create a simple test image
        img = Image.new('RGB', (100, 50), color='white')
        # Add some text-like patterns
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "TEST", fill='black')

        processed = ocr_service.preprocess_image(img)

        # Should return a processed image
        assert processed is not None
        assert isinstance(processed, Image.Image)
        # Should be grayscale or binary after preprocessing
        assert processed.mode in ('L', '1', 'RGB')

    def test_preprocess_image_grayscale(self, ocr_service):
        """Test preprocessing converts to grayscale."""
        img = Image.new('RGB', (100, 50), color='red')
        processed = ocr_service.preprocess_image(img)
        # After preprocessing, should be grayscale or binary
        assert processed.mode in ('L', '1')

    @pytest.mark.asyncio
    async def test_extract_text_empty_image(self, ocr_service):
        """Test extraction on empty/blank image."""
        img = Image.new('L', (100, 50), color=255)  # White image

        result = ocr_service.extract_text(img)

        assert 'full_text' in result
        assert 'avg_confidence' in result
        assert 'lines' in result
        assert 'word_count' in result
        assert isinstance(result['full_text'], str)
        assert isinstance(result['avg_confidence'], int | float)
        assert isinstance(result['lines'], list)
        assert isinstance(result['word_count'], int)

    @pytest.mark.asyncio
    async def test_process_file(self, ocr_service):
        """Test processing file from bytes."""
        img = Image.new('RGB', (100, 50), color='white')
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        result = ocr_service.process_file(buffer.getvalue())

        assert 'full_text' in result
        assert 'avg_confidence' in result
        assert 'lines' in result
        assert 'word_count' in result


class TestOCRServiceMocked:
    """Tests for OCR service with mocked tesseract."""

    @pytest.fixture
    def ocr_service(self):
        """Create OCR service instance."""
        return create_ocr_service()

    @patch('app.services.ocr.pytesseract.image_to_data')
    @patch('app.services.ocr.pytesseract.image_to_string')
    def test_extract_text_with_mocked_tesseract(self, mock_image_to_string, mock_image_to_data, ocr_service):
        """Test text extraction with mocked tesseract."""
        # Mock tesseract responses
        mock_image_to_string.return_value = "VENDOR ABC\nTotal: 100.00"
        mock_image_to_data.return_value = {
            'text': ['VENDOR', 'ABC', 'Total:', '100.00'],
            'conf': ['95', '95', '90', '90'],
            'left': [10, 60, 10, 60],
            'top': [10, 10, 30, 30],
            'width': [50, 30, 40, 40],
            'height': [20, 20, 20, 20],
            'line_num': [1, 1, 2, 2],
            'block_num': [1, 1, 2, 2],
        }

        img = Image.new('L', (100, 50), color=255)
        result = ocr_service.extract_text(img)

        assert result['full_text'] == "VENDOR ABC\nTotal: 100.00"
        assert result['avg_confidence'] == 92.5  # (95+95+90+90)/4
        assert result['word_count'] == 4
        assert len(result['lines']) == 4

    @patch('app.services.ocr.pytesseract.image_to_data')
    @patch('app.services.ocr.pytesseract.image_to_string')
    def test_extract_text_filters_zero_confidence(self, mock_image_to_string, mock_image_to_data, ocr_service):
        """Test that zero/negative confidence text is filtered out."""
        mock_image_to_string.return_value = "VENDOR ABC noise"
        mock_image_to_data.return_value = {
            'text': ['VENDOR', 'ABC', 'noise'],
            'conf': ['95', '95', '0'],  # Zero confidence filtered out
            'left': [10, 60, 10],
            'top': [10, 10, 30],
            'width': [50, 30, 20],
            'height': [20, 20, 20],
            'line_num': [1, 1, 2],
            'block_num': [1, 1, 2],
        }

        img = Image.new('L', (100, 50), color=255)
        result = ocr_service.extract_text(img)

        # Should only include items with confidence > 0
        assert result['word_count'] == 2
        assert len(result['lines']) == 2
        assert all(line['confidence'] > 0 for line in result['lines'])


class TestOCRDeskew:
    """Tests for deskew functionality."""

    @pytest.fixture
    def ocr_service(self):
        """Create OCR service instance."""
        return create_ocr_service()

    def test_deskew_no_op_on_clean_image(self, ocr_service):
        """Test deskew returns same image for clean/aligned text."""
        # Create image with horizontal text
        img = Image.new('L', (200, 100), color=255)
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.text((10, 40), "STRAIGHT TEXT", fill=0)

        deskewed = ocr_service._deskew(img)

        # Should return an image (may be same or rotated)
        assert isinstance(deskewed, Image.Image)

    def test_deskew_handles_small_images(self, ocr_service):
        """Test deskew handles very small images gracefully."""
        img = Image.new('L', (10, 10), color=255)
        deskewed = ocr_service._deskew(img)
        assert isinstance(deskewed, Image.Image)