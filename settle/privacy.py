"""Small, dependency-free redaction utilities for audit output."""
from __future__ import annotations
import re

_PHONE = re.compile(r"(?<!\d)(?:\+?254|0)7\d{8}(?!\d)")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_KEY = re.compile(r"(?i)(?:sk-ant-|sk-proj-|sk-)[A-Za-z0-9_-]{12,}")

def redact(text: str) -> str:
    """Mask obvious phone numbers, emails, and known API-key patterns."""
    value = _PHONE.sub("[PHONE]", text)
    value = _EMAIL.sub("[EMAIL]", value)
    return _KEY.sub("[SECRET]", value)
