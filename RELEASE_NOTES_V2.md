# Syllable Player V2

V2 replaces slow whole-word TTS playback with a pronunciation-learning pipeline built around a single full-word recording and phoneme-level alignment.

## Highlights

- Aligns grapheme chunks, phoneme chunks, and audio time ranges.
- Uses CMUdict pronunciations with G2P fallback for out-of-vocabulary words.
- Uses Montreal Forced Aligner to obtain phoneme timestamps from the full-word recording.
- Plays pronunciation chunks in sequence, then plays the complete word.
- Synchronizes spelling and IPA highlighting with actual audio playback.
- Adds boundary padding, fades, and chunk grouping to reduce clipped consonants and audible clicks.
- Caches generated analyses and audio for faster repeat playback.
- Includes a PySide6 desktop interface, favorites, examples, and automated tests.

## Verified example

For `everyone`, the application produces three learning chunks comparable to:

- `eve` ↔ `/ˈev/`
- `ry` ↔ `/ri/`
- `one` ↔ `/wʌn/`

The exact timestamps are derived from the selected recording rather than hard-coded.

## Installation

Run `setup.ps1` on Windows to create the local environment and install the required pronunciation resources. Then start the application with `run.bat` or `run.ps1`.

Large local dependencies, acoustic models, cached recordings, and generated audio are intentionally excluded from the repository.
