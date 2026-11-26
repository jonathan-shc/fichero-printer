"""Minimal Code 128 encoder (code sets B and C), no external dependencies."""

from __future__ import annotations

# Bar/space widths for symbol values 0-106 (103-105 start codes, 106 stop).
_PATTERNS = (
    "212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 "
    "221312 231212 112232 122132 122231 113222 123122 123221 223211 221132 "
    "221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 "
    "212123 212321 232121 111323 131123 131321 112313 132113 132311 211313 "
    "231113 231311 112133 112331 132131 113123 113321 133121 313121 211331 "
    "231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 "
    "314111 221411 431111 111224 111422 121124 121421 141122 141221 112214 "
    "112412 122114 122411 142112 142211 241211 221114 413111 241112 134111 "
    "111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 "
    "214121 412121 111143 111341 131141 114113 114311 411113 411311 113141 "
    "114131 311141 411131 211412 211214 211232 2331112"
).split()

START_B, START_C, CODE_B, STOP = 104, 105, 100, 106


def _values(data: str) -> list[int]:
    if not data:
        raise ValueError("Barcode content cannot be empty")
    if any(not 32 <= ord(char) <= 126 for char in data):
        raise ValueError("Barcodes support printable ASCII characters only")
    if data.isdigit() and len(data) >= 4:
        # Code set C packs two digits per symbol; an odd trailing digit is
        # finished in code set B.
        even = len(data) - len(data) % 2
        values = [START_C, *(int(data[i : i + 2]) for i in range(0, even, 2))]
        if even < len(data):
            values += [CODE_B, ord(data[-1]) - 32]
        return values
    return [START_B, *(ord(char) - 32 for char in data)]


def code128_modules(data: str) -> list[bool]:
    """Return the symbol as modules (True = bar), without quiet zones."""
    values = _values(data)
    checksum = (values[0] + sum(i * value for i, value in enumerate(values[1:], 1))) % 103
    modules: list[bool] = []
    for value in [*values, checksum, STOP]:
        bar = True
        for width in _PATTERNS[value]:
            modules.extend([bar] * int(width))
            bar = not bar
    return modules
