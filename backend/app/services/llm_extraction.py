"""LLM extraction service with provider abstraction (OpenAI, Gemini, Anthropic)."""

import json
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ExtractionResult(BaseModel):
    """Structured extraction result from LLM."""

    vendor_name: str | None = None
    vendor_gstin: str | None = None
    transaction_date: str | None = None
    invoice_number: str | None = None
    subtotal: float | None = None
    tax_amount: float | None = None
    total_amount: float | None = None
    currency: str = "INR"
    payment_method: str | None = None
    cgst_amount: float | None = None
    sgst_amount: float | None = None
    igst_amount: float | None = None
    hsn_sac_code: str | None = None
    irn: str | None = None
    line_items: list[dict[str, Any]] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0)
    raw_response: str | None = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def extract(self, ocr_text: str, prompt_template: str) -> ExtractionResult:
        """Extract structured data from OCR text."""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Get the model name for this provider."""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI GPT provider."""

    def __init__(self) -> None:
        self.api_key = settings.OPENAI_API_KEY
        self.model = settings.OPENAI_MODEL
        self.base_url = "https://api.openai.com/v1"

    async def extract(self, ocr_text: str, prompt_template: str) -> ExtractionResult:
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")

        prompt = prompt_template.format(ocr_text=ocr_text)

        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an expert at extracting structured expense data from OCR text. Return only valid JSON.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": settings.LLM_TEMPERATURE,
                    "max_tokens": settings.LLM_MAX_TOKENS,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        return self._parse_response(content)

    def get_model_name(self) -> str:
        return self.model

    def _parse_response(self, content: str) -> ExtractionResult:
        try:
            data = json.loads(content)
            return ExtractionResult(**data, raw_response=content)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse OpenAI response as JSON", error=str(e), content=content)
            raise ValueError(f"Invalid JSON response from OpenAI: {e}") from e


class GeminiProvider(LLMProvider):
    """Google Gemini provider."""

    def __init__(self) -> None:
        self.api_key = settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    async def extract(self, ocr_text: str, prompt_template: str) -> ExtractionResult:
        if not self.api_key:
            raise ValueError("Gemini API key not configured")

        prompt = prompt_template.format(ocr_text=ocr_text)

        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self.base_url}/models/{self.model}:generateContent",
                params={"key": self.api_key},
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": prompt}],
                        }
                    ],
                    "generationConfig": {
                        "temperature": settings.LLM_TEMPERATURE,
                        "maxOutputTokens": settings.LLM_MAX_TOKENS,
                        "responseMimeType": "application/json",
                    },
                },
            )
            response.raise_for_status()
            data = response.json()

        content = data["candidates"][0]["content"]["parts"][0]["text"]
        return self._parse_response(content)

    def get_model_name(self) -> str:
        return self.model

    def _parse_response(self, content: str) -> ExtractionResult:
        try:
            data = json.loads(content)
            return ExtractionResult(**data, raw_response=content)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse Gemini response as JSON", error=str(e), content=content)
            raise ValueError(f"Invalid JSON response from Gemini: {e}") from e


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""

    def __init__(self) -> None:
        self.api_key = settings.ANTHROPIC_API_KEY
        self.model = settings.ANTHROPIC_MODEL
        self.base_url = "https://api.anthropic.com/v1"

    async def extract(self, ocr_text: str, prompt_template: str) -> ExtractionResult:
        if not self.api_key:
            raise ValueError("Anthropic API key not configured")

        prompt = prompt_template.format(ocr_text=ocr_text)

        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{self.base_url}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": settings.LLM_MAX_TOKENS,
                    "temperature": settings.LLM_TEMPERATURE,
                    "system": "You are an expert at extracting structured expense data from OCR text. Return only valid JSON.",
                    "messages": [
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            response.raise_for_status()
            data = response.json()

        content = data["content"][0]["text"]
        return self._parse_response(content)

    def get_model_name(self) -> str:
        return self.model

    def _parse_response(self, content: str) -> ExtractionResult:
        try:
            data = json.loads(content)
            return ExtractionResult(**data, raw_response=content)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse Anthropic response as JSON", error=str(e), content=content)
            raise ValueError(f"Invalid JSON response from Anthropic: {e}") from e


class LLMProviderFactory:
    """Factory for creating LLM providers."""

    _providers: dict[str, type[LLMProvider]] = {
        "openai": OpenAIProvider,
        "gemini": GeminiProvider,
        "anthropic": AnthropicProvider,
    }

    @classmethod
    def create(cls, provider_name: str | None = None) -> LLMProvider:
        name = provider_name or settings.LLM_PROVIDER
        provider_class = cls._providers.get(name.lower())
        if not provider_class:
            raise ValueError(f"Unknown LLM provider: {name}. Available: {list(cls._providers.keys())}")
        return provider_class()

    @classmethod
    def register_provider(cls, name: str, provider_class: type[LLMProvider]) -> None:
        cls._providers[name.lower()] = provider_class


# Prompt template for expense extraction
EXPENSE_EXTRACTION_PROMPT = """
Extract structured expense data from the following OCR text. Return only valid JSON with these fields:
- vendor_name: string or null
- vendor_gstin: string (15 chars) or null
- transaction_date: string (YYYY-MM-DD) or null
- invoice_number: string or null
- subtotal: number or null
- tax_amount: number or null
- total_amount: number or null
- currency: string (default "INR")
- payment_method: string (CASH, UPI, BANK_TRANSFER, CARD, CHEQUE, OTHER) or null
- cgst_amount: number or null
- sgst_amount: number or null
- igst_amount: number or null
- hsn_sac_code: string or null
- irn: string or null
- line_items: array of objects with description, quantity, unit_price, amount, tax_amount
- confidence_score: number between 0.0 and 1.0

OCR Text:
{ocr_text}

Important:
- For Indian GST invoices, CGST+SGST = intra-state, IGST = inter-state
- Payment method: infer from text (UPI, NEFT, RTGS, IMPS = BANK_TRANSFER; cash = CASH; card = CARD)
- GSTIN is 15 chars: 2 state + 10 PAN + 1 entity + 1 checksum + 1
- If amounts not clear, use null and lower confidence
- Confidence: 0.9+ for clear invoices, 0.5-0.8 for partial, <0.5 for unclear
"""


class LLMextractionService:
    """Service for LLM-based expense extraction."""

    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or LLMProviderFactory.create()

    async def extract_expense(self, ocr_text: str) -> ExtractionResult:
        """Extract expense data from OCR text using LLM."""
        if not ocr_text or not ocr_text.strip():
            return ExtractionResult(
                confidence_score=0.0,
                raw_response="Empty OCR text",
            )

        try:
            result = await self.provider.extract(ocr_text, EXPENSE_EXTRACTION_PROMPT)
            logger.info(
                "LLM extraction completed",
                provider=self.provider.get_model_name(),
                confidence=result.confidence_score,
            )
            return result
        except Exception as e:
            logger.error("LLM extraction failed", error=str(e))
            raise


def create_llm_extraction_service() -> LLMextractionService:
    """Factory for creating LLMextractionService."""
    return LLMextractionService()
