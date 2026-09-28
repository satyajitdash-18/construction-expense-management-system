"""Tests for LLM extraction service."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

from app.services.llm_extraction import (
    LLMProviderFactory,
    OpenAIProvider,
    GeminiProvider,
    AnthropicProvider,
    LLMextractionService,
    ExtractionResult,
    create_llm_extraction_service,
    EXPENSE_EXTRACTION_PROMPT,
)
from app.services.validation import ValidationService, create_validation_service


class TestExtractionResult:
    """Tests for ExtractionResult model."""

    def test_valid_extraction_result(self):
        """Test creating valid extraction result."""
        result = ExtractionResult(
            vendor_name="Test Vendor",
            vendor_gstin="29AAAAA0000A1Z5",
            transaction_date="2026-09-20",
            invoice_number="INV-001",
            subtotal=1000.00,
            tax_amount=180.00,
            total_amount=1180.00,
            currency="INR",
            payment_method="UPI",
            cgst_amount=90.00,
            sgst_amount=90.00,
            igst_amount=None,
            hsn_sac_code="998314",
            irn=None,
            line_items=[
                {"description": "Item 1", "quantity": 2, "unit_price": 500.00, "amount": 1000.00, "tax_amount": 180.00}
            ],
            confidence_score=0.95,
            raw_response='{"vendor_name": "Test Vendor"}',
        )

        assert result.vendor_name == "Test Vendor"
        assert result.confidence_score == 0.95
        assert len(result.line_items) == 1

    def test_confidence_score_bounds(self):
        """Test confidence score validation."""
        with pytest.raises(ValueError):
            ExtractionResult(confidence_score=1.5)

        with pytest.raises(ValueError):
            ExtractionResult(confidence_score=-0.1)

    def test_default_values(self):
        """Test default values."""
        result = ExtractionResult(confidence_score=0.5)
        assert result.currency == "INR"
        assert result.line_items == []


class TestLLMProviderFactory:
    """Tests for LLM provider factory."""

    def test_create_openai_provider(self):
        """Test creating OpenAI provider."""
        with patch('app.services.llm_extraction.settings.OPENAI_API_KEY', 'test-key'):
            provider = LLMProviderFactory.create("openai")
            assert isinstance(provider, OpenAIProvider)
            assert provider.get_model_name() == "gpt-4o-mini"

    def test_create_gemini_provider(self):
        """Test creating Gemini provider."""
        with patch('app.services.llm_extraction.settings.GEMINI_API_KEY', 'test-key'):
            provider = LLMProviderFactory.create("gemini")
            assert isinstance(provider, GeminiProvider)
            assert provider.get_model_name() == "gemini-1.5-flash"

    def test_create_anthropic_provider(self):
        """Test creating Anthropic provider."""
        with patch('app.services.llm_extraction.settings.ANTHROPIC_API_KEY', 'test-key'):
            provider = LLMProviderFactory.create("anthropic")
            assert isinstance(provider, AnthropicProvider)
            assert provider.get_model_name() == "claude-3-haiku-20240307"

    def test_create_unknown_provider(self):
        """Test creating unknown provider raises error."""
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            LLMProviderFactory.create("unknown")

    def test_register_custom_provider(self):
        """Test registering custom provider."""
        class CustomProvider:
            async def extract(self, ocr_text, prompt_template):
                pass
            def get_model_name(self):
                return "custom"

        LLMProviderFactory.register_provider("custom", CustomProvider)
        provider = LLMProviderFactory.create("custom")
        assert isinstance(provider, CustomProvider)


class TestLLMextractionService:
    """Tests for LLM extraction service."""

    @pytest.fixture
    def mock_provider(self):
        """Create mock LLM provider."""
        provider = AsyncMock()
        provider.extract = AsyncMock(return_value=ExtractionResult(
            vendor_name="Test Vendor",
            vendor_gstin="29AAAAA0000A1Z5",
            transaction_date="2026-09-20",
            invoice_number="INV-001",
            subtotal=1000.00,
            tax_amount=180.00,
            total_amount=1180.00,
            currency="INR",
            payment_method="UPI",
            confidence_score=0.95,
            raw_response='{"vendor_name": "Test Vendor"}',
        ))
        provider.get_model_name = MagicMock(return_value="gpt-4o-mini")
        return provider

    @pytest.fixture
    def extraction_service(self, mock_provider):
        """Create extraction service with mock provider."""
        return LLMextractionService(provider=mock_provider)

    @pytest.mark.asyncio
    async def test_extract_expense_success(self, extraction_service, mock_provider):
        """Test successful expense extraction."""
        ocr_text = "VENDOR ABC\nTotal: 100.00"
        result = await extraction_service.extract_expense(ocr_text)

        assert isinstance(result, ExtractionResult)
        assert result.vendor_name == "Test Vendor"
        assert result.confidence_score == 0.95
        mock_provider.extract.assert_called_once_with(ocr_text, EXPENSE_EXTRACTION_PROMPT)

    @pytest.mark.asyncio
    async def test_extract_expense_empty_text(self, extraction_service):
        """Test extraction with empty OCR text."""
        result = await extraction_service.extract_expense("")
        assert result.confidence_score == 0.0
        assert result.raw_response == "Empty OCR text"

    @pytest.mark.asyncio
    async def test_extract_expense_whitespace_only(self, extraction_service):
        """Test extraction with whitespace only OCR text."""
        result = await extraction_service.extract_expense("   \n\t  ")
        assert result.confidence_score == 0.0

    @pytest.mark.asyncio
    async def test_extract_expense_provider_error(self, extraction_service, mock_provider):
        """Test handling of provider errors."""
        mock_provider.extract.side_effect = Exception("API Error")

        with pytest.raises(Exception, match="API Error"):
            await extraction_service.extract_expense("VENDOR ABC")


class TestOpenAIProvider:
    """Tests for OpenAI provider."""

    @pytest.fixture
    def provider(self):
        """Create OpenAI provider with test API key."""
        with patch('app.services.llm_extraction.settings.OPENAI_API_KEY', 'test-key'):
            with patch('app.services.llm_extraction.settings.OPENAI_MODEL', 'gpt-4o-mini'):
                return OpenAIProvider()

    @pytest.mark.asyncio
    async def test_extract_success(self, provider):
        """Test successful extraction."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"vendor_name": "Test Vendor", "confidence_score": 0.95}'
                }
            }]
        }
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await provider.extract("OCR text", EXPENSE_EXTRACTION_PROMPT)

            assert isinstance(result, ExtractionResult)
            assert result.vendor_name == "Test Vendor"
            assert result.confidence_score == 0.95

    @pytest.mark.asyncio
    async def test_extract_invalid_json(self, provider):
        """Test handling of invalid JSON response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {"content": "Not valid JSON"}
            }]
        }
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            with pytest.raises(ValueError, match="Invalid JSON response"):
                await provider.extract("OCR text", EXPENSE_EXTRACTION_PROMPT)

    @pytest.mark.asyncio
    async def test_extract_missing_api_key(self):
        """Test error when API key is missing."""
        with patch('app.services.llm_extraction.settings.OPENAI_API_KEY', ''):
            provider = OpenAIProvider()

            with pytest.raises(ValueError, match="OpenAI API key not configured"):
                await provider.extract("OCR text", EXPENSE_EXTRACTION_PROMPT)


class TestValidationService:
    """Tests for validation service."""

    @pytest.fixture
    def validation_service(self):
        """Create validation service."""
        return create_validation_service()

    def test_validate_valid_extraction(self, validation_service):
        """Test validation of valid extraction."""
        extraction = ExtractionResult(
            vendor_name="Test Vendor",
            vendor_gstin="29AAAAA0000A1Z5",
            transaction_date="2026-09-20",
            subtotal=1000.00,
            tax_amount=180.00,
            total_amount=1180.00,
            currency="INR",
            payment_method="UPI",
            confidence_score=0.95,
        )

        result = validation_service.validate(extraction)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_invalid_gstin(self, validation_service):
        """Test validation fails for invalid GSTIN."""
        extraction = ExtractionResult(
            vendor_name="Test Vendor",
            vendor_gstin="INVALID_GSTIN",
            transaction_date="2026-09-20",
            subtotal=1000.00,
            tax_amount=180.00,
            total_amount=1180.00,
            confidence_score=0.95,
        )

        result = validation_service.validate(extraction)

        assert result.is_valid is False
        assert any("GSTIN" in e for e in result.errors)
        assert result.confidence_adjustment < 0

    def test_validate_amount_mismatch(self, validation_service):
        """Test validation fails for amount mismatch."""
        extraction = ExtractionResult(
            vendor_name="Test Vendor",
            transaction_date="2026-09-20",
            subtotal=1000.00,
            tax_amount=180.00,
            total_amount=1200.00,  # Should be 1180
            confidence_score=0.95,
        )

        result = validation_service.validate(extraction)

        assert result.is_valid is False
        assert any("Amount mismatch" in e for e in result.errors)

    def test_validate_gst_breakdown(self, validation_service):
        """Test GST breakdown validation."""
        extraction = ExtractionResult(
            vendor_name="Test Vendor",
            transaction_date="2026-09-20",
            subtotal=1000.00,
            tax_amount=180.00,
            total_amount=1180.00,
            cgst_amount=100.00,
            sgst_amount=100.00,  # CGST + SGST = 200 != tax_amount 180
            confidence_score=0.95,
        )

        result = validation_service.validate(extraction)

        assert result.is_valid is False
        assert any("CGST" in e and "SGST" in e for e in result.errors)

    def test_validate_igst_interstate(self, validation_service):
        """Test IGST validation for interstate."""
        extraction = ExtractionResult(
            vendor_name="Test Vendor",
            transaction_date="2026-09-20",
            subtotal=1000.00,
            tax_amount=180.00,
            total_amount=1180.00,
            igst_amount=200.00,  # Should equal tax_amount for interstate
            confidence_score=0.95,
        )

        result = validation_service.validate(extraction)

        assert result.is_valid is False
        assert any("IGST" in e for e in result.errors)

    def test_validate_missing_required_fields(self, validation_service):
        """Test validation with missing required fields."""
        extraction = ExtractionResult(
            confidence_score=0.95,
        )

        result = validation_service.validate(extraction)

        # Missing amounts produces an error
        assert result.is_valid is False
        assert any("No amounts provided" in e for e in result.errors)

    def test_adjust_confidence(self, validation_service):
        """Test confidence adjustment calculation."""
        extraction = ExtractionResult(
            vendor_name="Test Vendor",
            transaction_date="2026-09-20",
            total_amount=1180.00,
            confidence_score=0.95,
        )

        validation_result = validation_service.validate(extraction)
        adjusted = validation_service.adjust_confidence(extraction, validation_result)

        assert 0.0 <= adjusted <= 1.0
        # Should be blended with completeness (3/3 required fields = 1.0)
        assert adjusted > 0.9

    def test_validate_invalid_date_format(self, validation_service):
        """Test validation warns for invalid date format."""
        extraction = ExtractionResult(
            vendor_name="Test Vendor",
            transaction_date="2026/09/20",  # Wrong format (not in supported patterns)
            total_amount=1180.00,
            confidence_score=0.95,
        )

        result = validation_service.validate(extraction)

        assert any("Date format" in w for w in result.warnings)

    def test_validate_unknown_payment_method(self, validation_service):
        """Test validation warns for unknown payment method."""
        extraction = ExtractionResult(
            vendor_name="Test Vendor",
            transaction_date="2026-09-20",
            total_amount=1180.00,
            payment_method="UNKNOWN_METHOD",
            confidence_score=0.95,
        )

        result = validation_service.validate(extraction)

        assert any("Unknown payment method" in w for w in result.warnings)

    def test_validate_irn_length(self, validation_service):
        """Test validation warns for invalid IRN length."""
        extraction = ExtractionResult(
            vendor_name="Test Vendor",
            transaction_date="2026-09-20",
            total_amount=1180.00,
            irn="SHORT",  # Should be 64 chars
            confidence_score=0.95,
        )

        result = validation_service.validate(extraction)

        assert any("IRN" in w for w in result.warnings)

    def test_validate_hsn_sac_code(self, validation_service):
        """Test validation warns for invalid HSN/SAC code."""
        extraction = ExtractionResult(
            vendor_name="Test Vendor",
            transaction_date="2026-09-20",
            total_amount=1180.00,
            hsn_sac_code="ABC",  # Should be digits
            confidence_score=0.95,
        )

        result = validation_service.validate(extraction)

        assert any("HSN" in w for w in result.warnings)

    def test_validate_line_items(self, validation_service):
        """Test line item validation."""
        extraction = ExtractionResult(
            vendor_name="Test Vendor",
            transaction_date="2026-09-20",
            total_amount=1180.00,
            line_items=[
                {"description": "", "amount": 100},  # Missing description
                {"description": "Item 2", "amount": -50},  # Invalid amount
            ],
            confidence_score=0.95,
        )

        result = validation_service.validate(extraction)

        assert result.is_valid is False
        assert any("missing description" in e for e in result.errors)
        assert any("invalid amount" in e for e in result.errors)


class TestPaymentMethodNormalization:
    """Tests for payment method normalization."""

    @pytest.fixture
    def validation_service(self):
        """Create validation service."""
        return create_validation_service()

    @pytest.mark.parametrize("input_method,expected", [
        ("cash", "CASH"),
        ("CASH", "CASH"),
        ("upi", "UPI"),
        ("UPI", "UPI"),
        ("bank transfer", "BANK_TRANSFER"),
        ("NEFT", "BANK_TRANSFER"),
        ("RTGS", "BANK_TRANSFER"),
        ("IMPS", "BANK_TRANSFER"),
        ("card", "CARD"),
        ("credit card", "CARD"),
        ("cheque", "CHEQUE"),
        ("check", "CHEQUE"),
    ])
    def test_normalize_payment_method(self, validation_service, input_method, expected):
        """Test payment method normalization."""
        normalized = validation_service._normalize_payment_method(input_method)
        assert normalized == expected

    def test_normalize_unknown_payment_method(self, validation_service):
        """Test unknown payment method returns None."""
        normalized = validation_service._normalize_payment_method("UNKNOWN")
        assert normalized is None