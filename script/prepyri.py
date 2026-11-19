import re 
from pathlib import Path

try:
    from .layouts import load_config, validate_config, file_options, segment_texts, reconstruct
except ImportError:  # Direct invocation by GitHub Actions
    from layouts import load_config, validate_config, file_options, segment_texts, reconstruct
#import pandas # To be used if external RegEx is a wish
from datetime import datetime # For timestamps in the log

version = """
Current Version:
\t0.2.0-beta Pre-Papyri with extension Prep-Ryli
\t19/11/2026
\tCorvin Ziegeler & Eliese-Sophia Lincke"""

##------------------------------------
## Current Version:
## 19/11/2026 Corvin Ziegeler & Eliese-Sophia Lincke
## For the log of changes consider commit history. 
##------------------------------------

## All the Functions necessary: 
# substitute_simple = uses dictionary with pattern and replacements
# move_hyphens = moves hyphens to next line beginning
# count dots = counts dots and puts them infront
# annotate_lines = handles line based annotations (numbers and recto/verso)

## Potential Additions: 
# - Recto/Verso
# - More Papyri Names (from filename? as arg? from config?)
# - External RegEx?
    

##------------------------------------
## SUBSTITUTE SIMPLE
##------------------------------------

simsubs = {
    ## NUMBERS
    # Empty line ahead of 3d numbers?
    r"(?<!\n\n)^\d{3}$": r"\n\n\g<0>",
    # If necessary this might be outsourced to use on other texts as well.
    r"\n\s*\n(\d{3})\n": r"\n\nP.Mon.Epiph. \1\n",
    r"\A\d{3}": r"P.Mon.Epiph. \g<0>",

    ## SPECIAL CHARS
    r"⳨": "*rho-cross*",
    r"\+": "*stauros*",
    r"·": "*middot*",
    r"⳿": "*word-sep-apostrophe*",
    r"ⲓ̈": " ⲓ(¨)",
    r":": "*dipunct*",

    ## SQUARE BRACKETS
    r"^(?!.*\[.*\])(.+?)\](.*)$": r"[.?][\1]\2",  # Any line with glyphs before ]
    r"^\]": "[.?]",  # At beginning of line
    r"\[$": "[.?]",  # At End of line
    r"\[(?![]\s])[^\]\n]*$": r"\g<0>] [.?]",  # Opening bracket without closing
    r"^]": "[.?]",  # Additional pattern for right bracket at start
    r"\[[ ]*$": "[.?]",  # Catch [ followed by optional spaces at end
    
    # Brackets with whitespaces, goes through two steps. 
    r"(\[[^\s\]]+?)\s+\?": r"\1][?",  # Opening bracket with non-whitespace characters and ?
    r"\[\s*\?\s*\]": r"[?]",  # Brackets with only whitespace and ?

    ##NOTE:
    # Known issue: Abbreviations with hyphen and new line are not caught 
    # correctly. This might have to be moved to its own function checking for "- " 
    # at line beginnings.

    ## Abbreviations
    r"(\S+)/": r"(\1( ))",  # Abbreviations, any Nonwhitespace char + rest + /
    ##NOTE: 
    # Does not catch multiple like: //
}

def substitute_simple(txt, simple_subs, additional_subs=None):
    """step_simple(txt, simple_subs, additional_subs=None)
    replaces using a dictionary, MULTILINE enabled.

    Args: 
    - txt: String with text to be replaced
    - simple_subs: Dictionary with keys for patterns and values for replacement
    - additional_subs: To be added (Should allow parsing an external csv with 
    additional key-value-pairs

    Returns the modified string.
    """
    for pattern, replacement in simple_subs.items():
        txt = re.sub(pattern, replacement, txt, flags=re.MULTILINE)

    if additional_subs is not None: 
        for pattern, replacement in additional_subs.items():
            txt = re.sub(pattern,replacement, txt, flags=re.MULTILINE)
            
    return txt

##------------------------------------
## MOVE HYPHENS 
##------------------------------------

def move_hyphens(text):
    """move_hyphens(text)
    Moves hyphens from the end of lines to the start of the next line for consistent formatting.
    If the next line starts with Latin alphanumeric characters, moves the hyphen to the line after that instead.
    Adds a newline after hyphens moved to empty lines.

    Args:
        text (str): Input text with potential hyphenated line breaks.

    Returns:
        str: Text with hyphens properly repositioned.
    """
    lines = text.split("\n")
    # Covering inconsistent hyphen encoding
    # Add warning here to a warning function? - Flatten Hyphens before?
    hyphen_chars = ["-", "‐", "‑", "−", "–", "—", "―"]
    # --------------------------------------------------
    # Collecting all "moves", to avoid double processing
    moves = []
    for i in range(len(lines) - 1):
        for hyphen in hyphen_chars:
            # Check if line ends with hyphen, but don't process lines
            # that are only hyphen+space
            line_stripped = lines[i].strip()

            if line_stripped.endswith(hyphen) and not (
                line_stripped == hyphen or line_stripped == hyphen + " "
            ):
                target_line = i + 1

                # If next line starts with Latin alphanumeric and we're not at the end,
                # move the hyphen to the line after that
                if (
                    target_line < len(lines) - 1
                    and lines[target_line].strip()
                    # Needs both isalnum and isascii - because otherwise
                    # Coptic chars would be considered alnum or asteriks ascii
                    # the combination creates a filter that matches the
                    # Latin alphabet without Unicode range stuff.
                    and lines[target_line].strip()[0].isalnum()
                    and lines[target_line].strip()[0].isascii()
                ):
                    target_line = i + 2

                # Only add the move if target line is within bounds
                if target_line < len(lines):
                    moves.append((i, hyphen, target_line))
                break
    # --------------------------------------------------
    # Apply all moves at once
    for i, hyphen, target_line in moves:
        # Remove hyphen from the end of lines + clean trailing spaces
        lines[i] = lines[i].rstrip()
        if lines[i].endswith(hyphen):
            lines[i] = lines[i][:-1]

        # If target_line is empthy add a newline (hyphen on last line issue)
        # Otherwise add to next line
        if not lines[target_line].strip():
            lines[target_line] = hyphen + "\n"
        else:
            lines[target_line] = hyphen + lines[target_line]

    return "\n".join(lines)

##------------------------------------
## COUNTING DOTS 
##------------------------------------

def count_dots(txt, mask_patterns=None):
    """step_dots(txt, mask_patterns=None)
    Substitutes sequences of dots (with or without spaces between them) with a count followed by a single dot.
    Preserves patterns specified in mask_patterns from being modified.

    Args:
    - txt (str): The text to process
    - mask_patterns (list): List of regex patterns to mask/protect from dot counting
                            Defaults to P.Mon.Epiph.

    Preserves surrounding whitespace and newlines.

    Returns string.
    """
    # Default mask pattern, this could also be added as read from a config?
    # maybe this is a great use for a toml?
    if mask_patterns is None:
        mask_patterns = [r"P\.Mon\.Epiph\.\s*\d+"]
    # -------------------------------------------
    # Step 1: Find and temporarily mask title patterns and [.?]
    masked_text = re.sub(r"(\[\.\?])", r"QUICKMASK", txt, flags=re.MULTILINE)
    # masked_text = txt
    placeholders = {}
    placeholder_counter = 0

    # Process each pattern in the mask_patterns list
    for pattern in mask_patterns:
        matches = re.finditer(pattern, masked_text)

        # Replace each match with placeholder+number
        # save the match in placeholders to overlay them later
        for match in matches:
            placeholder = f"__MASKED_PATTERN_{placeholder_counter}__"
            placeholder_counter += 1
            placeholders[placeholder] = match.group(0)
            masked_text = masked_text.replace(match.group(0), placeholder)
    # ------------------------------------------
    # Step 2: Process dots in the masked text
    dot_pattern = r"(\.[ ]*\.[ ]*\.+|\.[ ]*\.+|\.+)"

    def replace_dots(match):
        dot_sequence = match.group(0)
        dot_count = dot_sequence.count(".")
        return f".{dot_count}"

    processed_text = re.sub(dot_pattern, replace_dots, masked_text)

    # -------------------------------------------
    # Step 3: Overlay the placeholders with the originals
    for placeholder, original in placeholders.items():
        processed_text = processed_text.replace(placeholder, original)

    processed_text = re.sub(r"QUICKMASK", r"[.?]", processed_text)
    return processed_text

##------------------------------------
## ANNOTATE LINES (Multiple Functions)
## - split_lines
## - line_number_list
## - annotate_lines
##------------------------------------

# Splitting Fragments at empty lines
def split_lines(splitl):
    frag_list = []
    current_frag = []

    for line in splitl:
        # Check for end of frag = empty line
        if line == "\n":
            # Append to the fragment list
            current_frag.append(line)
            frag_list.append(current_frag)
            # reset current_frag
            current_frag = []
        # If not add to current fragment
        else:
            current_frag.append(line)
    if current_frag:
        frag_list.append(current_frag)
    return(frag_list)

# Ensure correct whitespacing  with hyphens, usinged in line_number_list
def ensure_hyphen_whitespace(line):
    # maybe flatte hyphens earlier?
    pattern = r"(?<=\d\.)\s+(?=[-‐‑−–—―])"
    # Remove space between . and - 
    result = re.sub(pattern, '', line)
    # Add a space between - and following char 
    result = re.sub(r"(?<=\d\.)([-‐‑−–—―])", r"\1 ", result)
    return result

# Line Number Magic
# Perhaps include the Recto/Verso Detection in here directly?
def line_number_list(lst):
    result = lst[:]  # Copy the original list
    warning = False
    warnings_str = ""
    i = 0
    last_number = None
    while i < len(result):
        item = result[i].strip()
        # ---------------------------------
        # Found a number
        if item.isdigit():
            num = int(item)
            last_number = num
            result.pop(i)  # Removing the item with the number
            if i < len(result):
                result[i] = f"{num}. {result[i]}"  # Move the number to the next line
            j = i - 1
            num -= 1
            while (
                j >= 0
                and not result[j].strip().isdigit()
                and not (  # Check if Alphanumberical
                    result[j].strip()[:1].isalnum() and result[j].strip()[:1].isascii()
                )
                and result[j].strip()
            ):  
                if num <= 0 and warning != True: 
                    warnings_str = warnings_str + f"\tLine Number Warning: {lst[0]} \twith line numbers below 1.\n"
                    warning = True
                result[j] = f"{num}. {result[j]}"  # Add number to before item
                num -= 1  # Move back number
                j -= 1  # Move back item
            # -----------------------------
            # Forward numbering after last number
            k = i + 1
            num = last_number + 1
            while (
                k < len(result)
                and not result[k].strip().isdigit()
                and not (
                    result[k].strip()[:1].isalnum() and result[k].strip()[:1].isascii()
                )
                and result[k].strip()
            ):
                result[k] = f"{num}. {result[k]}"  # Add number
                num += 1  # Move up number
                k += 1  # Move up item
        else:
            i += 1

        # Fix whitespaces for hyphens
        result_clean = []
        for line in result: 
           result_clean.append(ensure_hyphen_whitespace(line)) 

    return result_clean, warnings_str



# The workflow that combines the above.
def annotate_lines(torep, linenumbers=True, rectoverso=False):
    """
    Takes a String, splits it at Fragment Headers, applies Line numbering, joins it back
    together. Returns a string.
    
    Recto/Verso support might be added. 

    Relies on "split_lines" and line_number_list"
    """
    #---------------------------
    # Handling Flags
    warnings = ""
    if rectoverso: 
        #print("Line Annotation: Recto/verso not yet implemented.")
        warnings = warnings + "Line Numbering (annotate_lines) args error: Recto/verso option not yet implemented."
    
    if linenumbers:
        #print("Line Annotation: Starting line numbering.")
        pass
    else:
        if not rectoverso:
            #print("Line Annotation: No options selected")
            warnings = warnings + "Line Numbering (annotate_lines) args error: No options selected."
        return
    # Step 1 - Splitting -------
    # True keeps the '\n'
    steps = split_lines(torep.splitlines(True))

    # Step 2 - Recto/Verso -----
    # To be Added?
                         
    # Step 3 - Line Numbers ----
    step_list = []
    for frag in steps:
        step_list.append(line_number_list(frag)[0])
        warnings = warnings + line_number_list(frag)[1] 
    # print("Line Annotation: Finished line numbering.")
    
    # Step 4 - Rejoining -------
    result = ""
    for frag_numbered in step_list:
        result = result + "".join(frag_numbered)
    
    return(result, warnings)
#
# def additional_warnings(string):
#     """additional_warnings(string)
#     Gives warnings that might explain potential issues, 
#     or most certainly need manual handling. 
#     - Double Slashes
#     - Chars that are out of ASCII/Coptic range
#     - Wrong Hyphen encodings 
#     Also gives information about odd Unicode Encodings. 
#
#     Args:
#     - full string of the text, pre-processing
#
#     Returns:
#     A string with all the Errors in Categories.
#     """
#
#     # if not in coptic + ascii range
#

def process_text(source, filename='', config=None):
    """Reconstruct each edition text, then apply the original editorial rules.

    Titles and standalone paratext are protected from dot counting and numbering.
    Returns (output, diagnostics), keeping the CLI and tests on the same path.
    """
    config = {} if config is None else config
    validate_config(config)
    options = file_options(config, filename)
    texts, warnings = segment_texts(source, filename, options)
    output = []
    # Heading substitutions were a segmentation heuristic, not editorial rules.
    editorial_subs = {pattern: replacement for pattern, replacement in simsubs.items()
                      if replacement not in (r'\n\n\g<0>', r'\n\nP.Mon.Epiph. \1\n', r'P.Mon.Epiph. \g<0>')}
    for text in texts:
        overrides = options.get('texts', {}).get(text.number or '_unidentified', {})
        rows, layout, notices = reconstruct(
            text, overrides.get('layout', options.get('layout', 'auto')),
            overrides.get('start_line'),
        )
        label = text.title or '[unidentified opening text]'
        warnings.append(f'{label}: layout={layout}, lines={sum(r.kind == "text" for r in rows)}')
        warnings.extend(f'{label}: {notice}' for notice in notices)
        # Run hyphen movement across original lines, excluding interposed paratext.
        body = [r for r in rows if r.kind == 'text']
        normalized = substitute_simple('\n'.join(r.text or '[.?]' for r in body), editorial_subs)
        normalized = count_dots(move_hyphens(normalized)).split('\n') if body else []
        if text.title:
            output.append(text.title)
        index = 0
        for row in rows:
            if row.kind == 'paratext':
                output.append(row.text)
            else:
                output.append(ensure_hyphen_whitespace(f'{row.number}. {normalized[index]}'))
                index += 1
        output.append('')
    return '\n'.join(output), '\n'.join(warnings)


def main(root=None, config_path=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parent.parent
    if config_path is not None and not Path(config_path).is_file():
        raise FileNotFoundError(config_path)
    config = load_config(config_path if config_path is not None else root / 'prepyri.json')
    for directory in ('in', 'out', 'log', 'archive'):
        (root / directory).mkdir(exist_ok=True)
    for source in sorted((root / 'in').glob('*.txt')):
        result, warnings = process_text(source.read_text(encoding='utf-8'), source.name, config)
        archived = root / 'archive' / source.name
        (root / 'out' / f'out_{source.name}').write_text(result, encoding='utf-8')
        log = f'{version}\n{datetime.now().isoformat(timespec="seconds")} {source.name}\n{warnings}\n{result[:400]}\n'
        with (root / 'log' / f'log_{datetime.now().date()}.txt').open('a', encoding='utf-8') as stream:
            stream.write(log)
        print(log)
        source.rename(archived)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Reconstruct and normalize OCR texts in in/.')
    parser.add_argument('--config', type=Path, help='Optional JSON configuration (default: prepyri.json)')
    args = parser.parse_args()
    main(config_path=args.config)
