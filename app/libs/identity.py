"""Pure, shared identity rules. No network or database dependencies."""
from decimal import Decimal
from difflib import SequenceMatcher
from hashlib import sha256
import re
import unicodedata


def normalize_title(value):
    value = unicodedata.normalize('NFKC', str(value or '')).casefold().strip()
    # Keep accents, digits and meaningful symbols (+ is not interchangeable with -).
    value = ''.join(' ' if unicodedata.category(c).startswith('P') else c for c in value)
    return ' '.join(value.split())


def fingerprint(value):
    return sha256(value.encode('utf-8')).hexdigest()


def title_keys(item):
    return {key for value in [item.get('title', ''), *title_aliases(item)]
            if isinstance(value, str) and (key := normalize_title(value))
            and key not in {'sem título', 'untitled'}}


def title_aliases(item):
    aliases = item.get('aliases') or []
    return [aliases] if isinstance(aliases, str) else aliases


def metadata(item):
    return {key: normalize_title(value) for key, value in {
        'year': item.get('year') or item.get('ano'),
        'author': item.get('author') or item.get('autor'),
        'artist': item.get('artist'), 'type': item.get('type'),
        'country': item.get('country'), 'edition': item.get('edition'),
    }.items() if value and str(value).casefold() not in {'unknown', 'não informado'}}


def compatible(left, right):
    a, b = metadata(left), metadata(right)
    return all(a[k] == b[k] for k in a.keys() & b.keys())


def match_confidence(left, right):
    if not compatible(left, right):
        return 0.0, 'conflicting_metadata'
    if title_keys(left) & title_keys(right):
        return 1.0, 'exact_alias'
    # Fuzzy is a suggestion only, never an automatic identity decision.
    score = max((SequenceMatcher(None, a, b).ratio() for a in title_keys(left)
                 for b in title_keys(right)), default=0)
    return min(score, .94), 'candidate' if score >= .85 else 'different'


def parse_chapter(value):
    """Return canonical text and optional exact decimal; never float a chapter ID."""
    raw = unicodedata.normalize('NFKC', str(value if value is not None else '')).strip()
    if re.fullmatch(r'\d+(?:\.\d+)*', raw):
        if raw.count('.') <= 1:
            number = Decimal(raw)
            # NUMERIC(24, 8): retain longer values in text without silent rounding.
            numeric = number if len(number.as_tuple().digits) <= 24 and number.as_tuple().exponent >= -8 and number < 10**16 else None
            return (format(number, 'f').rstrip('0').rstrip('.') or '0') if '.' in raw else str(int(raw)), numeric
        return '.'.join(str(int(part)) for part in raw.split('.')), None
    return normalize_title(raw), None


def chapter_order(value):
    key, _ = parse_chapter(value)
    if re.fullmatch(r'\d+(?:\.\d+)*', key):
        # Decimal chapters before subdivisions, e.g. 12.5 < 12.5.1 < 13.
        parts = key.split('.')
        return (1, Decimal('.'.join(parts[:2])), tuple(int(p) for p in parts[2:]), '')
    if key in {'', 'none', 'sem número'}:
        return (-1, Decimal(0), (), '')
    if key in {'prologue', 'prólogo', 'prologo'}:
        return (0, Decimal(0), (), key)
    pieces = re.split(r'(\d+)', key)
    natural = ''.join(part.zfill(20) if part.isdigit() else part for part in pieces)
    return (3 if key in {'epilogue', 'epílogo', 'epilogo'} else 2, Decimal(0), (), natural)


def chapter_identity(number, volume=None, title=None, discriminator=None):
    key, numeric = parse_chapter(number)
    label = key if key not in {'', 'none', 'sem número'} else 'Sem número'
    vol, _ = parse_chapter(volume)
    if volume is None or str(volume).casefold() in {'', 'none'}:
        vol = ''
    if key in {'', 'none', 'sem número', 'extra', 'side story'}:
        label = normalize_title(title)
        key = 'special:' + (label if label and label != key else str(discriminator))
    return (f'v:{vol}|c:{key}', label, numeric, vol)


def approximate_page(percent, page_count):
    return max(1, min(page_count, int(float(percent) * page_count))) if page_count > 0 else 0
