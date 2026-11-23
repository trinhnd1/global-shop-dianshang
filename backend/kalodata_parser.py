"""Locale-Aware Kalodata Value Parser & Hardened `.xlsx` (OOXML) Reader.

Mandatory Invariants (Spec Section 2, 6):
- `missing` (`—`, `-`, `""`, `N/A`), `locked` (`***`, `VIP`, `Upgrade`), and `unavailable` NEVER become `0`.
- `0` (`Decimal('0')`, `value_state='present'`) is emitted ONLY when the source explicitly displays zero (`0`, `0₫`, `$0`, `0%`).
- Preserves `raw_text`, `qualifier` (`exact`, `approximate`, `lower_bound`, `upper_bound`, `range`),
  `min_decimal`, `max_decimal`, `unit`, `currency`, and `estimation_kind='kalodata_estimated_or_reported'`.
- Handles `1.2K`, `1,2K`, `< 100`, `> 10K`, `10K+`, price/GMV ranges (`150K - 250K`, `$10 ~ $20`), `%`, `VND`/`USD`/`THB`,
  and flags genuinely ambiguous bare thousands/decimals (`1.234` with `decimal_locale='auto'` and no currency) instead of guessing.
- Genuine `.xlsx` parser (`zipfile` + safe XML parsing without external DTD/entities, entry/byte caps) — never renames CSV as XLSX.
"""
from decimal import Decimal, InvalidOperation
import io
import re
import xml.etree.ElementTree as ET
import zipfile

MAX_XLSX_BYTES = 15 * 1024 * 1024
MAX_XLSX_ENTRIES = 60

MISSING_TOKENS = frozenset({"", "-", "--", "—", "–", "n/a", "na", "null", "none", "missing"})
LOCKED_PATTERNS = re.compile(
    r"^(\*{2,}|🔒|lock(?:ed)?|vip(?:\s*only)?|pro\s*only|upgrade(?:\s+to\s+view)?|nâng\s*cấp(?:\s*gói)?|subscribe\s+to\s+unlock)$",
    re.IGNORECASE,
)
UNAVAILABLE_PATTERNS = re.compile(r"^(unavailable|not\s+available|không\s+khả\s+dụng)$", re.IGNORECASE)

CURRENCY_SYMBOLS = (
    ("S$", "SGD"),
    ("US$", "USD"),
    ("VNĐ", "VND"),
    ("VND", "VND"),
    ("₫", "VND"),
    ("USD", "USD"),
    ("$", "USD"),
    ("THB", "THB"),
    ("฿", "THB"),
    ("IDR", "IDR"),
    ("Rp", "IDR"),
    ("MYR", "MYR"),
    ("RM", "MYR"),
    ("PHP", "PHP"),
    ("₱", "PHP"),
    ("SGD", "SGD"),
    ("CNY", "CNY"),
    ("RMB", "CNY"),
    ("¥", "CNY"),
    ("￥", "CNY"),
)

SUFFIX_MULTIPLIERS = (
    ("tỷ", Decimal("1000000000")),
    ("ty", Decimal("1000000000")),
    ("bn", Decimal("1000000000")),
    ("b", Decimal("1000000000")),
    ("亿", Decimal("100000000")),
    ("triệu", Decimal("1000000")),
    ("tr", Decimal("1000000")),
    ("mn", Decimal("1000000")),
    ("m", Decimal("1000000")),
    ("万", Decimal("10000")),
    ("nghìn", Decimal("1000")),
    ("k", Decimal("1000")),
    ("w", Decimal("10000")),
)

RANGE_SPLIT_RE = re.compile(r"\s*(?:~|–|—|\bto\b|(?<=\d|[A-Za-z₫$%])\s*-\s*)\s*", re.IGNORECASE)
AMBIGUOUS_SINGLE_SEP_RE = re.compile(r"^[+-]?\d{1,3}([.,])\d{3}$")


def _extract_currency_and_unit(s: str) -> tuple[str, str, str]:
    """Return `(cleaned_without_unit, detected_currency, unit)`."""
    work = s.strip()
    detected_curr = ""
    unit = ""

    if work.endswith("%"):
        unit = "pct"
        work = work[:-1].strip()

    for sym, code in CURRENCY_SYMBOLS:
        if sym.lower() in work.lower():
            detected_curr = code
            if not unit:
                unit = code
            pattern = re.compile(re.escape(sym), re.IGNORECASE)
            work = pattern.sub("", work).strip()
            break

    # Standalone trailing Vietnamese 'đ' currency marker (avoiding words)
    if not detected_curr and re.search(r"(?<=\d)\s*đ$", work, re.IGNORECASE):
        detected_curr = "VND"
        unit = unit or "VND"
        work = re.sub(r"\s*đ$", "", work, flags=re.IGNORECASE).strip()

    return work, detected_curr, unit


def _parse_single_number_token(
    token: str,
    decimal_locale: str = "auto",
    currency_hint: str = "",
) -> tuple[Decimal | None, bool, bool]:
    """Return `(decimal_val, is_approximate_suffix, is_locale_ambiguous)`."""
    t = token.strip()
    if not t:
        return None, False, False

    mult = Decimal("1")
    is_approx = False
    low = t.lower()
    for sfx, factor in SUFFIX_MULTIPLIERS:
        if low.endswith(sfx) and len(t) > len(sfx):
            prev_ch = low[-len(sfx) - 1]
            if prev_ch.isdigit() or prev_ch in (" ", ".", ","):
                mult = factor
                is_approx = True
                t = t[:-len(sfx)].strip()
                break

    # Checklocale ambiguity on bare `1.234` or `1,234` when `decimal_locale == 'auto'` and no suffix/currency disambiguates!
    m_amb = AMBIGUOUS_SINGLE_SEP_RE.fullmatch(t)
    if m_amb and not is_approx and decimal_locale == "auto" and not currency_hint:
        return None, False, True

    if "," in t and "." in t:
        # Both separators present -> rightmost one is unambiguously the decimal separator!
        if t.rfind(",") > t.rfind("."):
            norm = t.replace(".", "").replace(",", ".")
        else:
            norm = t.replace(",", "")
    elif "," in t:
        if is_approx:
            # e.g. `1,2K` or `1,25Tr` -> comma is decimal separator!
            norm = t.replace(",", ".")
        elif decimal_locale == "vi":
            norm = t.replace(",", ".")
        elif decimal_locale == "en":
            norm = t.replace(",", "")
        elif currency_hint in ("USD", "SGD"):
            # `$1,200` -> thousands separator
            parts = t.split(",")
            norm = t.replace(",", "") if all(len(p) == 3 for p in parts[1:]) else t.replace(",", ".")
        else:
            parts = t.split(",")
            norm = t.replace(",", "") if (len(parts) > 2 or len(parts[-1]) == 3) else t.replace(",", ".")
    elif "." in t:
        if is_approx:
            # e.g. `1.2K` -> dot is decimal separator
            norm = t
        elif decimal_locale == "vi" or currency_hint in ("VND", "IDR"):
            parts = t.split(".")
            if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
                norm = t.replace(".", "")
            else:
                norm = t
        else:
            parts = t.split(".")
            norm = t.replace(".", "") if len(parts) > 2 else t
    else:
        norm = t

    norm = norm.replace(" ", "")
    try:
        d = Decimal(norm) * mult
        if not d.is_finite():
            return None, is_approx, False
        return d, is_approx, False
    except InvalidOperation:
        return None, is_approx, False


def parse_kalodata_display_cell(
    raw_val,
    expected_currency: str = "",
    decimal_locale: str = "auto",
    is_estimated_metric: bool = True,
) -> dict:
    """Parse a Kalodata display cell while preserving raw string, state, bounds, and approximate/range flags."""
    if raw_val is None:
        return {
            "raw_text": "",
            "value_state": "missing",
            "qualifier": "not_applicable",
            "value_decimal": None,
            "min_decimal": None,
            "max_decimal": None,
            "currency": "",
            "unit": "",
            "approximate": False,
            "estimation_kind": "kalodata_estimated_or_reported" if is_estimated_metric else "observed",
        }

    if isinstance(raw_val, bool):
        return {
            "raw_text": str(raw_val),
            "value_state": "missing",
            "qualifier": "not_applicable",
            "value_decimal": None,
            "min_decimal": None,
            "max_decimal": None,
            "currency": "",
            "unit": "",
            "approximate": False,
            "estimation_kind": "kalodata_estimated_or_reported" if is_estimated_metric else "observed",
        }

    if isinstance(raw_val, (int, Decimal)):
        d = Decimal(raw_val)
        return {
            "raw_text": str(raw_val),
            "value_state": "present" if d.is_finite() else "missing",
            "qualifier": "exact",
            "value_decimal": str(d) if d.is_finite() else None,
            "min_decimal": None,
            "max_decimal": None,
            "currency": expected_currency,
            "unit": expected_currency,
            "approximate": False,
            "estimation_kind": "kalodata_estimated_or_reported" if is_estimated_metric else "observed",
        }

    if isinstance(raw_val, float):
        d = Decimal(str(raw_val))
        return {
            "raw_text": str(raw_val),
            "value_state": "present" if d.is_finite() else "missing",
            "qualifier": "exact",
            "value_decimal": str(d) if d.is_finite() else None,
            "min_decimal": None,
            "max_decimal": None,
            "currency": expected_currency,
            "unit": expected_currency,
            "approximate": False,
            "estimation_kind": "kalodata_estimated_or_reported" if is_estimated_metric else "observed",
        }

    raw_s = str(raw_val).strip()
    if raw_s.lower() in MISSING_TOKENS:
        return {
            "raw_text": raw_s,
            "value_state": "missing",
            "qualifier": "not_applicable",
            "value_decimal": None,
            "min_decimal": None,
            "max_decimal": None,
            "currency": "",
            "unit": "",
            "approximate": False,
            "estimation_kind": "kalodata_estimated_or_reported" if is_estimated_metric else "observed",
        }

    if LOCKED_PATTERNS.match(raw_s) or "***" in raw_s or "🔒" in raw_s:
        return {
            "raw_text": raw_s,
            "value_state": "locked",
            "qualifier": "not_applicable",
            "value_decimal": None,
            "min_decimal": None,
            "max_decimal": None,
            "currency": "",
            "unit": "",
            "approximate": False,
            "estimation_kind": "kalodata_estimated_or_reported" if is_estimated_metric else "observed",
        }

    if UNAVAILABLE_PATTERNS.match(raw_s):
        return {
            "raw_text": raw_s,
            "value_state": "unavailable",
            "qualifier": "not_applicable",
            "value_decimal": None,
            "min_decimal": None,
            "max_decimal": None,
            "currency": "",
            "unit": "",
            "approximate": False,
            "estimation_kind": "kalodata_estimated_or_reported" if is_estimated_metric else "observed",
        }

    work, det_curr, det_unit = _extract_currency_and_unit(raw_s)
    eff_curr = det_curr or expected_currency

    # 1. Check Inequality Bounds (`< 100`, `<= 50`, `> 10K`, `>= 1K`, `10K+`)
    if work.startswith((">=", "≥")) or work.startswith(">") or work.endswith("+"):
        inner = work.lstrip(">≥= ").rstrip("+ ").strip()
        d, is_apx, is_amb = _parse_single_number_token(inner, decimal_locale=decimal_locale, currency_hint=eff_curr)
        if is_amb:
            return {
                "raw_text": raw_s,
                "value_state": "ambiguous_locale",
                "qualifier": "lower_bound",
                "value_decimal": None,
                "min_decimal": None,
                "max_decimal": None,
                "currency": det_curr,
                "unit": det_unit,
                "approximate": True,
                "estimation_kind": "kalodata_estimated_or_reported",
            }
        if d is not None:
            return {
                "raw_text": raw_s,
                "value_state": "present",
                "qualifier": "lower_bound",
                "value_decimal": str(d),
                "min_decimal": str(d),
                "max_decimal": None,
                "currency": det_curr or expected_currency,
                "unit": det_unit or eff_curr,
                "approximate": True,
                "estimation_kind": "kalodata_estimated_or_reported" if is_estimated_metric else "observed",
            }

    if work.startswith(("<=", "≤")) or work.startswith("<"):
        inner = work.lstrip("<≤= ").strip()
        d, is_apx, is_amb = _parse_single_number_token(inner, decimal_locale=decimal_locale, currency_hint=eff_curr)
        if d is not None and not is_amb:
            # Upper bound (e.g. `< 100`) -> value_decimal is None (NEVER 0 and NEVER 100!), max_decimal preserved!
            return {
                "raw_text": raw_s,
                "value_state": "present",
                "qualifier": "upper_bound",
                "value_decimal": None,
                "min_decimal": None,
                "max_decimal": str(d),
                "currency": det_curr or expected_currency,
                "unit": det_unit or eff_curr,
                "approximate": True,
                "estimation_kind": "kalodata_estimated_or_reported" if is_estimated_metric else "observed",
            }

    # 2. Check Range (`150K - 250K`, `₫120.000 ~ ₫180.000`)
    range_parts = RANGE_SPLIT_RE.split(raw_s)
    if len(range_parts) == 2 and not raw_s.startswith("-"):
        w1, c1, u1 = _extract_currency_and_unit(range_parts[0])
        w2, c2, u2 = _extract_currency_and_unit(range_parts[1])
        rcurr = c1 or c2 or expected_currency
        d1, _, amb1 = _parse_single_number_token(w1, decimal_locale=decimal_locale, currency_hint=rcurr)
        d2, _, amb2 = _parse_single_number_token(w2, decimal_locale=decimal_locale, currency_hint=rcurr)
        if d1 is not None and d2 is not None and not amb1 and not amb2:
            lo, hi = (d1, d2) if d1 <= d2 else (d2, d1)
            return {
                "raw_text": raw_s,
                "value_state": "present",
                "qualifier": "range",
                "value_decimal": None,
                "min_decimal": str(lo),
                "max_decimal": str(hi),
                "currency": c1 or c2 or expected_currency,
                "unit": u1 or u2 or rcurr,
                "approximate": True,
                "estimation_kind": "kalodata_estimated_or_reported" if is_estimated_metric else "observed",
            }

    # 3. Single Scalar Value
    d, is_apx, is_amb = _parse_single_number_token(work, decimal_locale=decimal_locale, currency_hint=eff_curr)
    if is_amb:
        return {
            "raw_text": raw_s,
            "value_state": "ambiguous_locale",
            "qualifier": "not_applicable",
            "value_decimal": None,
            "min_decimal": None,
            "max_decimal": None,
            "currency": det_curr,
            "unit": det_unit,
            "approximate": False,
            "estimation_kind": "kalodata_estimated_or_reported" if is_estimated_metric else "observed",
        }
    if d is None:
        return {
            "raw_text": raw_s,
            "value_state": "unparseable",
            "qualifier": "not_applicable",
            "value_decimal": None,
            "min_decimal": None,
            "max_decimal": None,
            "currency": det_curr,
            "unit": det_unit,
            "approximate": False,
            "estimation_kind": "kalodata_estimated_or_reported" if is_estimated_metric else "observed",
        }

    return {
        "raw_text": raw_s,
        "value_state": "present",
        "qualifier": "approximate" if is_apx else "exact",
        "value_decimal": str(d),
        "min_decimal": None,
        "max_decimal": None,
        "currency": det_curr or expected_currency,
        "unit": det_unit or eff_curr,
        "approximate": is_apx,
        "estimation_kind": "kalodata_estimated_or_reported" if is_estimated_metric else "observed",
    }


def _safe_parse_xml(xml_bytes: bytes) -> ET.Element:
    """Reject XML external entities / DOCTYPE declarations before parsing OOXML parts."""
    head = xml_bytes[:4096].upper()
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise ValueError("Từ chối tệp XLSX chứa khai báo XML DOCTYPE/ENTITY không an toàn")
    return ET.fromstring(xml_bytes)


def _xlsx_col_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha()).upper()
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return max(0, idx - 1)


def parse_xlsx_bytes(raw_bytes: bytes) -> list[dict]:
    """Parse a genuine `.xlsx` OOXML workbook safely with ZIP entry/size guards (rejects renamed CSVs)."""
    if len(raw_bytes) > MAX_XLSX_BYTES:
        raise ValueError("Tệp XLSX vượt quá giới hạn an toàn 15 MB")
    if not raw_bytes.startswith(b"PK\x03\x04"):
        raise ValueError("Tệp .xlsx không đúng định dạng OOXML hợp lệ (không chấp nhận tệp CSV đổi đuôi thành .xlsx)")

    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as zf:
            infos = zf.infolist()
            if len(infos) > MAX_XLSX_ENTRIES:
                raise ValueError(f"Tệp XLSX chứa quá nhiều thành phần nội bộ (>{MAX_XLSX_ENTRIES})")
            total_uncompressed = sum(i.file_size for i in infos)
            if total_uncompressed > MAX_XLSX_BYTES * 2:
                raise ValueError("Dung lượng giải nén XLSX vượt ngưỡng an toàn (nghi ngờ ZIP bomb)")

            names = set(zf.namelist())
            if "[Content_Types].xml" not in names:
                raise ValueError("Tệp ZIP không phải sổ tính Excel (.xlsx) hợp lệ")

            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in names:
                ss_root = _safe_parse_xml(zf.read("xl/sharedStrings.xml"))
                for si in ss_root.iter():
                    if si.tag.endswith("}si") or si.tag == "si":
                        texts = [t.text or "" for t in si.iter() if t.tag.endswith("}t") or t.tag == "t"]
                        shared_strings.append("".join(texts))

            sheet_candidates = sorted(n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
            if not sheet_candidates:
                raise ValueError("Không tìm thấy trang tính dữ liệu (worksheet) trong tệp XLSX")

            ws_root = _safe_parse_xml(zf.read(sheet_candidates[0]))
            matrix: list[list[str]] = []
            for row_el in ws_root.iter():
                if not (row_el.tag.endswith("}row") or row_el.tag == "row"):
                    continue
                row_vals: dict[int, str] = {}
                max_c = -1
                for c_el in row_el:
                    if not (c_el.tag.endswith("}c") or c_el.tag == "c"):
                        continue
                    c_ref = c_el.attrib.get("r", "")
                    c_idx = _xlsx_col_index(c_ref) if c_ref else (max_c + 1)
                    max_c = max(max_c, c_idx)
                    c_type = c_el.attrib.get("t", "")
                    val_txt = ""
                    if c_type == "inlineStr":
                        val_txt = "".join(t.text or "" for t in c_el.iter() if t.tag.endswith("}t") or t.tag == "t")
                    else:
                        v_el = next((ch for ch in c_el if ch.tag.endswith("}v") or ch.tag == "v"), None)
                        if v_el is not None and v_el.text is not None:
                            if c_type == "s":
                                s_idx = int(v_el.text)
                                val_txt = shared_strings[s_idx] if 0 <= s_idx < len(shared_strings) else ""
                            else:
                                val_txt = v_el.text
                    row_vals[c_idx] = val_txt.strip()
                if max_c >= 0:
                    dense = [row_vals.get(i, "") for i in range(max_c + 1)]
                    if any(cell != "" for cell in dense):
                        matrix.append(dense)
    except zipfile.BadZipFile:
        raise ValueError("Tệp .xlsx bị hỏng hoặc không phải tệp OOXML hợp lệ") from None

    if not matrix:
        return []
    headers = [h.strip() or f"col_{idx + 1}" for idx, h in enumerate(matrix[0])]
    out_rows = []
    for r in matrix[1:]:
        row_dict = {}
        for idx, h in enumerate(headers):
            row_dict[h] = r[idx] if idx < len(r) else ""
        out_rows.append(row_dict)
    return out_rows
