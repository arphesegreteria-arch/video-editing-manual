# Carabellese local verification — 2026-10-12

Scope: PC_PERSONALE only. No media, transcript, credentials, or render output is stored here.

## Verified work

* Audio worker provenance emits verified `silence_windows`; analysis consumes them
  without relaxing the 33 ms timing tolerance.
* Sample-clock provenance was checked against the 48 kHz stereo WAV.
* Zero-length tokens stay immutable and prevent adjacent derived cuts.
* Draft application uses an isolated Resolve timeline and staging tracks; source
  timelines and the canonical job stay unchanged.
* Focused audio-pipeline, analysis, and draft suites passed locally (24 tests in
  the last combined run).

## Draft/render evidence

Private V3 preserves P002/P003/P008 and contains reviewed pause cuts
P001/P004/P005/P006/P007/P009/P010. Container timing in its private 480p
preview was within 3 ms. PCM comparison is an objective signal check only; no
subjective listening claim is made, so perceived distortion is not resolved.

## Filler alignment pilot

VAD-off ASR candidates were review-only and did not provide safe cut coordinates.
An isolated WhisperX 3.8.6 CPU environment (outside bridge/Resolve) used
PyTorch/Torchaudio 2.8.0 and the Italian VoxPopuli base-10k alignment model.
No media left the PC.

The corrected pipeline reads the validated WAV by sequential sample index:
48 kHz stereo s16 -> mono -> 16 kHz. Known-text positive control aligned at
0.614--0.945 word score; wrong-text negative control was mostly 0.171--0.595.
The approved E001--E005 filler context scored 0--0.646 with unverified text,
so no filler cut was applied.

Future filler gate: reviewed known text, same PCM representation as cut source,
monotonic high-confidence bounds with phoneme guards, private recap, and exact
cut approval. WhisperX aligns known text; it does not discover omitted fillers.
