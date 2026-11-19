# Original OCR regression fixtures

- `PMonEpiph_170-172_2026-11-17.txt`: byte-for-byte copy of the fork's archived
  input. Expected three texts, all wysiwyg, with 9 / 36 / 22 body lines.
  Text 171 contains interleaved material and repeated counters (10 and 15).
  Tests require preservation in source order and explicit conflict diagnostics,
  not an unsupported reconstruction of the edition's column order.
- `PRylCopt_320-329_2026-01-09.txt`: user-supplied OCR from the RSVP task,
  copied unchanged. Ten edition texts; 321 uses numbered lines and all others
  use pipes. Text 320 has 41 body lines, plus the inscription above line 1;
  321 has 10 body lines; 323 crosses an Element page boundary within line 2.
  Standalone and inline paratext, Coptic/Greek, footnote signs, brackets and both
  physical-wrap/original-line hyphens are covered by assertions.
- `PRylCopt_296-301_2026-11-18.txt`: user-supplied additional OCR, copied
  unchanged. The heading 298 is absent; the parser must not infer a new text
  from the page boundary. This differs from the older archived p141–p142 file,
  which also starts with an unidentified continuation.

Tests use explicit counts and selected independently inspected line contents,
not snapshots generated from the parser. Editorial normalization is not an OCR
correction: malformed `(ies0`, `(in ⲟtⲠⲉr direⲥtion` and the prose broken around
heading 329 are preserved. The tests do not claim a philological collation with
edition scans or implement details from the earlier ChatGPT project conversation.
