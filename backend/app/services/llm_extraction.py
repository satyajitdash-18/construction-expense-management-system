"""LLM extraction service with provider abstraction (OpenAI, Gemini, Anthropic)."""

import json
import re
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def extract_json_from_text(content: str) -> dict[str, Any]:
    """Robustly extract and parse a JSON dictionary from raw LLM text output."""
    if not content or not content.strip():
        raise ValueError("Empty LLM response content")

    text = content.strip()

    # 1. Direct json.loads
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. Markdown code fences (```json ... ``` or ``` ... ```)
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    matches = fence_pattern.findall(text)
    for candidate in matches:
        candidate_clean = candidate.strip()
        try:
            data = json.loads(candidate_clean)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            cleaned = re.sub(r",\s*([\]}])", r"\1", candidate_clean)
            try:
                data = json.loads(cleaned)
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, TypeError):
                pass

    # 3. Outermost JSON object substring: from first '{' to last '}'
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        json_str = text[start_idx : end_idx + 1].strip()
        try:
            data = json.loads(json_str)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            cleaned = re.sub(r",\s*([\]}])", r"\1", json_str)
            try:
                data = json.loads(cleaned)
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, TypeError):
                pass

    raise ValueError(f"Could not extract valid JSON object from LLM response: {content[:200]}")


class ExtractionResult(BaseModel):
    """Structured extraction result from LLM."""

    vendor_name: str | None = None
    vendor_gstin: str | None = None
    transaction_date: str | None = None
    invoice_number: str | None = None
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    currency: str = "INR"
    payment_method: str | None = None
    cgst_amount: Decimal | None = None
    sgst_amount: Decimal | None = None
    igst_amount: Decimal | None = None
    hsn_sac_code: str | None = None
    irn: str | None = None
    line_items: list[dict[str, Any]] = Field(default_factory=list)
    confidence_score: float = Field(default=0.85, ge=0.0, le=1.0)
    raw_response: str | None = None

    model_config = ConfigDict(extra="ignore")

    @field_serializer("total_amount", "subtotal", "tax_amount", "cgst_amount", "sgst_amount", "igst_amount")
    def serialize_decimal(self, v: Decimal | None) -> float | None:
        return float(v) if v is not None else None

    def validate_financial_invariants(self) -> tuple[bool, str | None]:
        """Validate mathematical invariants deterministically using strict Decimal arithmetic."""
        if self.total_amount is None:
            return False, "Total amount is missing"
        if self.total_amount < Decimal("0"):
            return False, "Total amount is negative"

        sub = self.subtotal if self.subtotal is not None else self.total_amount
        tax = self.tax_amount if self.tax_amount is not None else Decimal("0.00")

        if sub < Decimal("0") or tax < Decimal("0"):
            return False, "Subtotal or tax amount is negative"

        # Deterministic mathematical invariant: subtotal + tax must equal total exactly
        if (sub + tax) != self.total_amount:
            return False, f"Total ({self.total_amount}) does not match subtotal ({sub}) + tax ({tax})"

        # Check GST components if present
        cgst = self.cgst_amount or Decimal("0.00")
        sgst = self.sgst_amount or Decimal("0.00")
        igst = self.igst_amount or Decimal("0.00")
        if cgst < Decimal("0") or sgst < Decimal("0") or igst < Decimal("0"):
            return False, "GST amounts cannot be negative"

        if self.tax_amount is not None and (cgst > Decimal("0") or sgst > Decimal("0") or igst > Decimal("0")):
            if igst > Decimal("0"):
                if igst != self.tax_amount:
                    return False, f"IGST ({igst}) does not match tax amount ({self.tax_amount})"
            elif (cgst > Decimal("0") or sgst > Decimal("0")):
                if (cgst + sgst) != self.tax_amount:
                    return False, f"CGST ({cgst}) + SGST ({sgst}) does not match tax amount ({self.tax_amount})"

        return True, None


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

    def _parse_response(self, content: str) -> ExtractionResult:
        """Parse structured ExtractionResult from raw LLM output with robust fallbacks."""
        try:
            data = extract_json_from_text(content)
            # Normalize and clamp confidence_score
            if "confidence_score" in data and data["confidence_score"] is not None:
                try:
                    score = float(data["confidence_score"])
                    data["confidence_score"] = max(0.0, min(1.0, score))
                except (ValueError, TypeError):
                    data["confidence_score"] = 0.85
            else:
                data["confidence_score"] = 0.85

            # Quantize monetary fields to Decimal("0.01")
            for field in ("total_amount", "subtotal", "tax_amount", "cgst_amount", "sgst_amount", "igst_amount"):
                if field in data and data[field] is not None:
                    try:
                        data[field] = Decimal(str(data[field])).quantize(Decimal("0.01"))
                    except Exception:
                        data[field] = None

            return ExtractionResult(**data, raw_response=content)
        except Exception as e:
            logger.error("Failed to parse LLM response as JSON", error=str(e), content=content)
            raise ValueError(f"Invalid JSON response from LLM: {e}") from e


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
