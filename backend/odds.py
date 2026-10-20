"""Jen předzápasové (neuzavírací) kurzy. Sloupce s C (B365CH, PSCH, AvgCH…) se nepoužijí."""

BOOKS = (
    ("B365H", "B365D", "B365A"),
    ("BWH", "BWD", "BWA"),
    ("IWH", "IWD", "IWA"),
    ("WHH", "WHD", "WHA"),
    ("VCH", "VCD", "VCA"),
    ("LBH", "LBD", "LBA"),
    ("GBH", "GBD", "GBA"),
    ("SBH", "SBD", "SBA"),
    ("SJH", "SJD", "SJA"),
    ("PSH", "PSD", "PSA"),
    ("PH", "PD", "PA"),
    ("AvgH", "AvgD", "AvgA"),
)

def is_closing(column):
    name = str(column or "").upper()
    return name.endswith("CH") or name.endswith("CD") or name.endswith("CA")

def _num(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in {"NA", "NAN", "NONE"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number != number or number <= 1.01 or number >= 100:
        return None
    return number

def pick_odds(row):
    """Vrátí (home, draw, away) nebo None. Nikdy ne closing sloupce."""
    for cols in BOOKS:
        if any(is_closing(col) for col in cols):
            continue
        vals = [_num(row.get(col)) for col in cols]
        if all(vals):
            return vals
    return None

def implied(odds):
    if not odds:
        return None
    inv = [1.0 / o for o in odds]
    total = sum(inv)
    if total <= 0:
        return None
    return [v / total for v in inv]
