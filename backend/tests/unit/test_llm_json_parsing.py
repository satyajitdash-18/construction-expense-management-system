"""Unit tests for robust LLM JSON extraction and parsing."""

import pytest

from app.services.llm_extraction import (
    AnthropicProvider,
    GeminiProvider,
    OpenAIProvider,
    extract_json_from_text,
)


class DummyOpenAI(OpenAIProvider):
    def __init__(self):
        self.model = "gpt-4o-mini"


def test_clean_json_parsing():
    content = '{"vendor_name": "ABC Cement", "total_amount": 15000.0, "currency": "INR", "confidence_score": 0.95}'
    provider = DummyOpenAI()
    result = provider._parse_response(content)
    assert result.vendor_name == "ABC Cement"
    assert result.total_amount == 15000.0
    assert result.confidence_score == 0.95


def test_markdown_json_code_fence():
    content = """```json
{
    "vendor_name": "Steel Corp",
    "total_amount": 25000.0,
    "confidence_score": 0.9
}
```"""
    provider = DummyOpenAI()
    result = provider._parse_response(content)
    assert result.vendor_name == "Steel Corp"
    assert result.total_amount == 25000.0
    assert result.confidence_score == 0.9


def test_markdown_fence_without_language_tag():
    content = """```
{
    "vendor_name": "Brick Supply",
    "total_amount": 8000.0
}
```"""
    provider = DummyOpenAI()
    result = provider._parse_response(content)
    assert result.vendor_name == "Brick Supply"
    assert result.total_amount == 8000.0
    assert result.confidence_score == 0.85  # default assigned


def test_conversational_preamble_and_postamble():
    content = """Here is the extracted invoice data from the document you provided:
```json
{
    "vendor_name": "Timber Traders",
    "total_amount": 12000.0,
    "invoice_number": "INV-2024-99"
}
```
Please let me know if you need anything else!"""
    provider = DummyOpenAI()
    result = provider._parse_response(content)
    assert result.vendor_name == "Timber Traders"
    assert result.total_amount == 12000.0
    assert result.invoice_number == "INV-2024-99"


def test_embedded_json_object_without_fences():
    content = (
        "Based on the receipt analysis: "
        '{"vendor_name": "Sand & Gravel Co", "total_amount": 3400.0, "payment_method": "CASH"} '
        "was successfully identified."
    )
    provider = DummyOpenAI()
    result = provider._parse_response(content)
    assert result.vendor_name == "Sand & Gravel Co"
    assert result.total_amount == 3400.0
    assert result.payment_method == "CASH"


def test_trailing_comma_repair():
    content = """```json
{
    "vendor_name": "Fix It Hardware",
    "total_amount": 500.0,
    "line_items": [
        {"description": "Nails", "amount": 500.0,},
    ],
}
```"""
    provider = DummyOpenAI()
    result = provider._parse_response(content)
    assert result.vendor_name == "Fix It Hardware"
    assert result.total_amount == 500.0
    assert len(result.line_items) == 1


def test_extra_fields_ignored():
    content = """{
    "vendor_name": "Tech Corp",
    "total_amount": 999.0,
    "unrecognized_field": "some notes",
    "audit_trail": [1, 2, 3]
}"""
    provider = DummyOpenAI()
    result = provider._parse_response(content)
    assert result.vendor_name == "Tech Corp"
    assert result.total_amount == 999.0


def test_confidence_score_clamping():
    # Value > 1.0 clamped to 1.0
    content1 = '{"vendor_name": "Test", "confidence_score": 1.5}'
    provider = DummyOpenAI()
    result1 = provider._parse_response(content1)
    assert result1.confidence_score == 1.0

    # Value < 0.0 clamped to 0.0
    content2 = '{"vendor_name": "Test", "confidence_score": -0.2}'
    result2 = provider._parse_response(content2)
    assert result2.confidence_score == 0.0


def test_invalid_non_json_raises_value_error():
    content = "Sorry, I am unable to read this invoice because it is completely blurry."
    provider = DummyOpenAI()
    with pytest.raises(ValueError, match="Could not extract valid JSON"):
        provider._parse_response(content)
