"""Validation service for extracted expense data with confidence scoring."""

import re
from decimal import Decimal

from app.schemas.extraction import ExtractionResponse, ExtractionValidationResult
from app.services.llm_extraction import ExtractionResult


class ValidationService:
    """Service for validating extracted expense data and adjusting confidence."""

    # Indian GSTIN regex: 2 state + 10 PAN + 1 entity + 1 checksum + 1
    GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[0-9A-Z]{1}Z[0-9A-Z]{1}$")

    # Indian PAN regex: 5 letters + 4 digits + 1 letter
    PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")

    # Date patterns
    DATE_PATTERNS = [
        re.compile(r"^\d{4}-\d{2}-\d{2}$"),  # YYYY-MM-DD
        re.compile(r"^\d{2}/\d{2}/\d{4}$"),  # DD/MM/YYYY
        re.compile(r"^\d{2}-\d{2}-\d{4}$"),  # DD-MM-YYYY
    ]

    # Payment method normalization
    PAYMENT_METHODS = {
        "cash": "CASH",
        "upi": "UPI",
        "bank transfer": "BANK_TRANSFER",
        "neft": "BANK_TRANSFER",
        "rtgs": "BANK_TRANSFER",
        "imps": "BANK_TRANSFER",
        "card": "CARD",
        "credit card": "CARD",
        "debit card": "CARD",
        "cheque": "CHEQUE",
        "check": "CHEQUE",
    }

    def validate(self, extraction: ExtractionResponse | ExtractionResult) -> ExtractionValidationResult:
        """Validate extraction and return validation result with confidence adjustment."""
        errors = []
        warnings = []
        confidence_adjustment = 0.0

        # Validate GSTIN
        if extraction.vendor_gstin:
            if not self.GSTIN_PATTERN.match(extraction.vendor_gstin.upper()):
                errors.append("Invalid GSTIN format")
                confidence_adjustment -= 0.1

        # Validate transaction date
        if extraction.transaction_date:
            if not any(p.match(extraction.transaction_date) for p in self.DATE_PATTERNS):
                warnings.append("Date format may be invalid (expected YYYY-MM-DD)")
                confidence_adjustment -= 0.05

        # Validate amounts consistency
        amount_errors = self._validate_amounts(extraction)
        errors.extend(amount_errors)
        if amount_errors:
            confidence_adjustment -= 0.15

        # Validate payment method
        if extraction.payment_method:
            normalized = self._normalize_payment_method(extraction.payment_method)
            if normalized:
                extraction.payment_method = normalized
            else:
                warnings.append(f"Unknown payment method: {extraction.payment_method}")
                confidence_adjustment -= 0.05

        # Validate IRN format (Invoice Reference Number - 64 chars)
        if extraction.irn and len(extraction.irn) != 64:
            warnings.append("IRN should be 64 characters")
            confidence_adjustment -= 0.05

        # Validate HSN/SAC code (typically 4-8 digits)
        if extraction.hsn_sac_code and not re.match(r"^\d{4,8}$", extraction.hsn_sac_code):
            warnings.append("HSN/SAC code should be 4-8 digits")
            confidence_adjustment -= 0.05

        # Validate line items
        if extraction.line_items:
            for i, item in enumerate(extraction.line_items):
                # Handle both dict (ExtractionResult) and LineItemExtraction (ExtractionResponse)
                if isinstance(item, dict):
                    desc = item.get("description")
                    amt = item.get("amount")
                else:
                    desc = getattr(item, "description", None)
                    amt = getattr(item, "amount", None)

                if not desc:
                    errors.append(f"Line item {i+1}: missing description")
                    confidence_adjustment -= 0.1
                if amt is not None and amt <= 0:
                    errors.append(f"Line item {i+1}: invalid amount")
                    confidence_adjustment -= 0.1

        # Validate currency
        if extraction.currency not in ["INR", "USD", "EUR"]:
            warnings.append(f"Unusual currency: {extraction.currency}")
            confidence_adjustment -= 0.02

        is_valid = len(errors) == 0
        _ = max(0.0, min(1.0, extraction.confidence_score + confidence_adjustment))

        return ExtractionValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            confidence_adjustment=confidence_adjustment,
        )

    def _validate_amounts(self, extraction: ExtractionResponse | ExtractionResult) -> list[str]:
        """Validate amount consistency."""
        errors = []

        subtotal = extraction.subtotal
        tax = extraction.tax_amount
        total = extraction.total_amount
        cgst = extraction.cgst_amount
        sgst = extraction.sgst_amount
        igst = extraction.igst_amount

        # Check if at least some amounts are present
        if subtotal is None and tax is None and total is None:
            return ["No amounts provided"]

        # If all three present, validate consistency
        if subtotal is not None and tax is not None and total is not None:
            expected_total = Decimal(str(subtotal)) + Decimal(str(tax))
            actual_total = Decimal(str(total))
            if abs(expected_total - actual_total) > Decimal("0.01"):
                errors.append(f"Amount mismatch: subtotal({subtotal}) + tax({tax}) != total({total})")

        # Validate GST breakdown
        if cgst is not None and sgst is not None and tax is not None:
            expected_tax = Decimal(str(cgst)) + Decimal(str(sgst))
            actual_tax = Decimal(str(tax))
            if abs(expected_tax - actual_tax) > Decimal("0.01"):
                errors.append(f"CGST({cgst}) + SGST({sgst}) != tax({tax})")

        if igst is not None and tax is not None and cgst is None and sgst is None:
            # Inter-state should have only IGST
            if abs(Decimal(str(igst)) - Decimal(str(tax))) > Decimal("0.01"):
                errors.append(f"IGST({igst}) != tax({tax}) for inter-state invoice")

        return errors

    def _normalize_payment_method(self, method: str) -> str | None:
        """Normalize payment method to standard enum."""
        normalized = method.strip().lower()
        return self.PAYMENT_METHODS.get(normalized)

    def adjust_confidence(self, extraction: ExtractionResponse | ExtractionResult, validation: ExtractionValidationResult) -> float:
        """Calculate final confidence after validation."""
        base_confidence = extraction.confidence_score
        adjusted = base_confidence + validation.confidence_adjustment

        # Additional adjustments based on completeness
        required_fields = [
            extraction.vendor_name,
            extraction.transaction_date,
            extraction.total_amount,
        ]
        filled = sum(1 for f in required_fields if f is not None)
        completeness = filled / len(required_fields)

        # Blend base confidence with completeness
        final = (adjusted * 0.7) + (completeness * 0.3)

        return max(0.0, min(1.0, final))


def create_validation_service() -> ValidationService:
    """Factory for creating ValidationService."""
    return ValidationService()
