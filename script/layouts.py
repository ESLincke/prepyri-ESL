"""OCR structure, before editorial normalization (standard library only).

Ambiguous OCR is retained and reported, never silently reordered or corrected.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

PAGE = re.compile(r'^\s*-*\s*Element\s+\d+\b.*$', re.I)
NUMBER = re.compile(r'^([0-9]+)\.?$')
TITLE = re.compile(r'^(P\.Mon\.Epiph\.|P\.Ryl\.Copt\.|Rylands Letters)\s+([0-9]+)\.?$')
HYPHENS = '-‐‑−–—―'
LAYOUTS = {'auto', 'wysiwyg', 'pipe', 'numbered'}


@dataclass
class Text:
    number: str | None
    title: str
    lines: list[str] = field(default_factory=list)


@dataclass
class Row:
    text: str
    kind: str = 'text'
    anchor: int | None = None
    number: int | None = None


def load_config(path):
    path = Path(path)
    config = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    validate_config(config)
    return config


def validate_config(config):
    if not isinstance(config, dict) or set(config) - {'files'}:
        raise ValueError('Configuration must be an object with a files mapping')
    files = config.get('files', {})
    if not isinstance(files, dict):
        raise ValueError('files must be an object')
    for name, options in files.items():
        if not isinstance(options, dict) or set(options) - {'layout', 'edition', 'edition_numbers', 'texts'}:
            raise ValueError(f'{name}: invalid file options')
        if 'edition' in options and not isinstance(options['edition'], str):
            raise ValueError(f'{name}: edition must be a string')
        if 'edition_numbers' in options and (
            not isinstance(options['edition_numbers'], list)
            or any(not re.fullmatch(r'[0-9]+', str(n)) for n in options['edition_numbers'])
        ):
            raise ValueError(f'{name}: edition_numbers must be a list of integers')
        texts = options.get('texts', {})
        if not isinstance(texts, dict):
            raise ValueError(f'{name}: texts must be an object')
        for opts in [options, *texts.values()]:
            if not isinstance(opts, dict) or not isinstance(opts.get('layout', 'auto'), str) or opts.get('layout', 'auto') not in LAYOUTS:
                raise ValueError(f'{name}: invalid layout options')
            if opts is not options and set(opts) - {'layout', 'start_line'}:
                raise ValueError(f'{name}: invalid text options')
            if 'start_line' in opts and (type(opts['start_line']) is not int or opts['start_line'] < 1):
                raise ValueError(f'{name}: start_line must be a positive integer')


def file_options(config, filename):
    return config.get('files', {}).get(Path(filename).name, {})


def is_paratext(line):
    # Latin prose, including OCR-corrupted Latin containing a few Coptic glyphs.
    # Bracketed illegibility/space notes belong to the transcription instead.
    stripped = line.lstrip()
    if stripped.startswith('['):
        return False
    latin = len(re.findall(r'[A-Za-z]', stripped))
    ancient = len(re.findall(r'[\u0370-\u03ff\u2c80-\u2cff]', stripped))
    return bool(re.match(r'^(?:[0-9⁰¹²³⁴⁵⁶⁷⁸⁹]+[.)]?\s+)?[A-Za-z(]', stripped)) or latin > max(8, ancient * 2)


def segment_texts(source, filename='', options=None):
    options = options or {}
    lines = [line.strip() for line in source.splitlines() if not PAGE.match(line)]
    candidates = [(i, int(m[1])) for i, line in enumerate(lines) if (m := NUMBER.fullmatch(line))]
    explicit = options.get('edition_numbers')
    # Existing corpus filenames enumerate nonconsecutive editions as well.
    # Page filenames (e.g. PRylCopt_p.141-p.142) deliberately do not qualify.
    filename_ids = set()
    listing = re.match(r'^(?:PMonEpiph|PRylCopt)_([0-9+.,-]+)_', Path(filename).name)
    if listing:
        for match in re.finditer(r'([0-9]+)(?:-([0-9]+))?', listing[1]):
            first, last = int(match[1]), int(match[2] or match[1])
            if first <= last <= first + 10000:
                filename_ids.update(range(first, last + 1))
    allowed = {int(n) for n in explicit} if explicit is not None else None
    # A run of line counters reaching 100 must not become edition headings.
    counter_positions = set()
    for (i, n), (j, following) in zip(candidates, candidates[1:]):
        if following == n + 1 and n < 100:
            counter_positions.update((i, j))
        elif following == n + 1 and i in counter_positions:
            counter_positions.add(j)
    high = {n for i, n in candidates if n >= 100 and i not in counter_positions}
    edition = options.get('edition')
    if edition is None:
        edition = 'P.Ryl.Copt.' if re.search(r'ryl|rylands', filename, re.I) else 'P.Mon.Epiph.' if 'PMonEpiph' in filename else ''
    texts, current, warnings = [], Text(None, ''), []
    for i, line in enumerate(lines):
        named = TITLE.fullmatch(line)
        bare = NUMBER.fullmatch(line)
        number = int(named[2]) if named else int(bare[1]) if bare else None
        heading = bool(named)
        if bare:
            if allowed is not None:
                heading = number in allowed
            else:
                # Three digits alone are insufficient: require edition context or
                # adjacent edition numbers, and exclude an established counter run.
                heading = i not in counter_positions and number >= 100 and (
                    number in filename_ids or number - 1 in high or number + 1 in high or (not texts and not any(current.lines))
                )
        if heading:
            if current.title or any(current.lines):
                texts.append(current)
            if current.number is not None and number > int(current.number) + 1:
                warnings.append(f'Edition number jumps from {current.number} to {number}; no missing heading was invented.')
            title = line if named else f'{edition} {number}'.strip()
            current = Text(str(number), title)
        else:
            current.lines.append(line)
            if bare and number >= 100 and i not in counter_positions:
                warnings.append(f'Ambiguous number {number} retained as a counter; use edition_numbers if it is a heading.')
    if current.title or any(current.lines):
        texts.append(current)
    if texts and texts[0].number is None:
        warnings.append('Unidentified opening text retained; no edition number was invented.')
    return texts, warnings


def detect_layout(lines):
    if any('|' in line and not is_paratext(line) for line in lines):
        return 'pipe'
    numbers = [int(m[1]) for line in lines if (m := NUMBER.fullmatch(line.strip()))]
    if len(numbers) >= 2 and sum(b == a + 1 for a, b in zip(numbers, numbers[1:])) >= max(1, len(numbers) - 2):
        return 'numbered'
    return 'wysiwyg'


def join_ocr(parts):
    """Join physical wraps; an OCR wrap hyphen is not an original-line hyphen."""
    result = ''
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if result and result[-1] in HYPHENS:
            result = result[:-1] + part
        else:
            result += (' ' if result else '') + part
    return result


def reconstruct(text, layout='auto', start_line=None):
    layout = detect_layout(text.lines) if layout == 'auto' else layout
    rows, pending, warnings = [], [], []
    anchor = None
    above = False

    def flush():
        nonlocal pending, anchor
        if not pending:
            return
        if layout == 'pipe':
            chunks = join_ocr(pending).split('|')
            # A trailing delimiter terminates a line, it does not add another.
            if not chunks[-1].strip():
                chunks.pop()
            for chunk in chunks:
                chunk = chunk.strip()
                marker = re.match(r'^([0-9]+)(?:[.]?\s+|(?=[-‐‑−–—―]))', chunk)
                n = int(marker[1]) if marker else None
                if marker:
                    chunk = chunk[marker.end():].strip()
                inline = re.match(r'^\((?:recto|verso)\)\s*', chunk, re.I)
                if inline:
                    rows.append(Row(inline[0].strip(), 'paratext'))
                    chunk = chunk[inline.end():]
                rows.append(Row(chunk, anchor=n))
        else:
            rows.append(Row(join_ocr(pending), anchor=anchor))
        pending, anchor = [], None

    for line in text.lines:
        if not line:
            continue
        if is_paratext(line) and '|' not in line:
            flush()
            rows.append(Row(line, 'paratext'))
            above = bool(re.match(r'Above\s+l\.', line, re.I))
            continue
        if above:
            rows.append(Row(line, 'paratext'))
            above = False
            continue
        marker = NUMBER.fullmatch(line)
        if marker and layout != 'pipe':
            flush()
            if anchor is not None:
                warnings.append(f'Unused line marker {anchor}')
            anchor = int(marker[1])
        elif layout == 'wysiwyg':
            rows.append(Row(line, anchor=anchor))
            anchor = None
        else:
            # An OCR note may follow the last pipe on a physical line. Preserve
            # it separately before joining the next physical transcription line.
            prefix, separator, tail = line.rpartition('|')
            if layout == 'pipe' and separator and is_paratext(tail.strip()):
                pending.append(prefix + '|')
                flush()
                rows.append(Row(tail.strip(), 'paratext'))
            else:
                pending.append(line)
    flush()
    if anchor is not None:
        warnings.append(f'Unused line marker {anchor}')
    body = [row for row in rows if row.kind == 'text']
    if start_line is None:
        first = next(((i, row.anchor) for i, row in enumerate(body) if row.anchor is not None), None)
        start_line = first[1] - first[0] if first else 1
        if start_line < 1:
            warnings.append(f'Anchor implies start {start_line}; numbering starts at 1 instead')
            start_line = 1
    for n, row in enumerate(body, start_line):
        row.number = n
        if row.anchor is not None and row.anchor != n:
            warnings.append(f'Conflicting line marker {row.anchor}; reconstructed line {n} retained')
    return rows, layout, warnings
