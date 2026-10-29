"""
barcode.py: Генерация и валидация штрихкодов EAN-13 для товаров Ozon.
"""

import re

# 29 (GS1 внутренний для предприятий) + 78 (код региона СПб) + 47 (Другой Петербург: D=4, P=7)
STORE_BARCODE_PREFIX = "297847"


def calc_ean13_checksum(digits12_str: str) -> int:
    """Вычисляет контрольную цифру GS1 EAN-13 для 12 цифр."""
    digits = [int(c) for c in str(digits12_str) if c.isdigit()]
    if len(digits) != 12:
        return 0
    s_odd = sum(digits[i] for i in range(0, 12, 2))
    s_even = sum(digits[i] for i in range(1, 12, 2))
    total = s_odd + s_even * 3
    return (10 - (total % 10)) % 10


def generate_ean13_from_article(article_str: str) -> str:
    """Генерирует валидный EAN-13 штрихкод из артикула вида DP-B-XXXXX с уникальным префиксом магазина."""
    digits = re.sub(r"\D", "", str(article_str or ""))
    try:
        num = int(digits)
        if num <= 0:
            num = 1
    except Exception:
        num = 1
    base12 = f"{STORE_BARCODE_PREFIX}{num:06d}"[-12:]
    check_digit = calc_ean13_checksum(base12)
    return f"{base12}{check_digit}"

