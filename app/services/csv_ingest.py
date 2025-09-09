# app/services/csv_ingest.py
from __future__ import annotations

import csv
import io
from typing import Dict, List, Tuple

REQUIRED_HEADER = "url"

# Map acceptable optional aliases (left) to canonical column names (right)
HEADER_ALIASES = {
    "telephone": "phone",   # accept "telephone" as "phone"
}

OPTIONAL_HEADERS = {
    "page_type",
    "topic",
    "subject",
    "audience",
    "address",
    "phone",         # canonical name (see alias above)
    "competitor1",
    "competitor2",
}


def _canonicalize_headers(header_row: List[str]) -> List[str]:
    """Lowercase, strip whitespace, and apply HEADER_ALIASES. Preserve order."""
    canonical: List[str] = []
    for h in header_row:
        key = (h or "").strip()
        key_lower = key.lower()
        key_lower = HEADER_ALIASES.get(key_lower, key_lower)
        canonical.append(key_lower)
    return canonical


def parse_csv3(text: str) -> Tuple[List[Dict[str, str]], List[str], List[str]]:
    """
    Parse CSV text and return (rows, errors, warnings).

    rows:     list of dicts with canonical headers
    errors:   fatal errors (should prevent starting batch)
    warnings: non-fatal issues (e.g., skipped empty-url rows)

    Required header:
      - url

    Optional headers (accepted if present):
      - page_type, topic, subject, audience, address, phone(or telephone), competitor1, competitor2
    """
    errors: List[str] = []
    warnings: List[str] = []
    rows: List[Dict[str, str]] = []

    if not text or not text.strip():
        return [], ["The uploaded CSV appears to be empty."], []

    # Use csv.Sniffer to handle common delimiters; fall back to default if sniff fails.
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample)
    except Exception:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect)
    try:
        raw_header = next(reader)
    except StopIteration:
        return [], ["The uploaded CSV has no header row."], []

    header = _canonicalize_headers(raw_header)

    # Validate required header
    if REQUIRED_HEADER not in header:
        return [], [
            "CSV is missing the required 'url' column. Please include a header row with at least: url"
        ], []

    # Build a mapping from index to canonical header name.
    idx_to_name: Dict[int, str] = {}
    for idx, name in enumerate(header):
        idx_to_name[idx] = name

    url_idx = header.index(REQUIRED_HEADER)

    valid_row_count = 0
    for line_num, raw_row in enumerate(reader, start=2):  # 1-based header at line 1
        if all((c or '').strip() == '' for c in raw_row):
            # Entirely blank line—skip silently
            continue

        # Normalize row length to header length
        if len(raw_row) < len(header):
            raw_row += [''] * (len(header) - len(raw_row))
        elif len(raw_row) > len(header):
            # Join extras into the last column to avoid losing data
            overflow = raw_row[len(header) - 1:]
            raw_row = raw_row[:len(header) - 1] + [','.join(overflow)]

        url_val = (raw_row[url_idx] or '').strip()
        if not url_val:
            warnings.append(f"Row {line_num} missing 'url' value; row skipped.")
            continue

        row_obj: Dict[str, str] = {}
        for idx, raw_val in enumerate(raw_row):
            key = idx_to_name[idx]
            val = (raw_val or '').strip()
            row_obj[key] = val

        # Ensure canonical phone key if "telephone" was supplied
        if 'telephone' in row_obj and 'phone' not in row_obj:
            row_obj['phone'] = row_obj.get('telephone', '')

        rows.append(row_obj)
        valid_row_count += 1

    if valid_row_count == 0:
        errors.append("No valid rows to process. Every row needs a non-empty 'url' value.")

    return rows, errors, warnings


def parse_csv(text: str):
    """Backward-compatible wrapper returning (rows, warnings).
    If there are fatal errors, they are prefixed and returned as warnings, and rows = [].
    This avoids breaking older call sites that expected a 2-tuple.
    """
    rows, errors, warnings = parse_csv3(text)
    if errors:
        prefixed = [f"ERROR: {e}" for e in errors]
        # Return no rows so upstream logic can short-circuit gracefully
        return [], prefixed + warnings
    return rows, warnings
