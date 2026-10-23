# Timeline Audio Caption Transcription Design

## Intent

Generate captions from the audio that is actually heard on an explicitly selected DaVinci Resolve timeline. This prevents removed source material or an unrelated transcript from appearing in captions.

## Goals

- Render a temporary 48 kHz PCM WAV from the complete selected timeline, audio only.
- Preserve the source timeline, project save state, render queue, current timeline, and prior render settings.
- Transcribe the rendered WAV with word timestamps and bind the transcript to a fingerprint of that WAV plus the timeline edit fingerprint.
- Require `create_caption_test` to verify this binding before duplicating or captioning a timeline.
- Keep the command generic: no project-, timeline-, or campaign-specific behavior.

## Non-goals

- Do not transcribe the uncut camera/source file.
- Do not infer edit spans or speakers.
- Do not save the Resolve project, render a publishable video, or change existing caption timelines.
- Do not update PC_SEGRETERIA in this change.

## Constraints

- PC_PERSONALE only for the live verification.
- The selected project and source timeline must be registered or explicitly allowlisted.
- The temporary audio and transcript stay inside bridge-managed roots.
- A mismatch in project, timeline identity, timeline edit fingerprint, audio fingerprint, duration, or workstation fails closed.
- The CTA remains excluded through the existing explicit caption cutoff.

## Approaches

1. **Audio-only Resolve render of the timeline — selected.** This captures the exact edit, seam treatment, clip gain, and audible ordering. It is the only approach that makes the timeline itself authoritative.
2. Reconstruct audio from source clip spans. Rejected because it can diverge from fades, fillers, track state, gain, and future Fairlight processing.
3. Transcribe the full source and map timestamps through edit spans. Rejected because it can leak removed speech and repeats the failure mode reported on `advbeppe`.

## Design

Add a managed timeline-transcription job with two read-safe phases. `start_timeline_audio_transcription` validates the current project and explicit timeline, saves the complete current Deliver state as a uniquely named temporary Resolve render preset, loads the native `Audio Only` preset, creates one uniquely identifiable WAV render job, then reloads and deletes the temporary restore preset before starting only the owned job. This is required because Resolve 21.1.1 exposes no `GetRenderSettings` API and can report an unset current format as `{"format": "unknown", "codec": ""}`. `get_timeline_audio_transcription_job` polls the render; after completion it verifies the WAV, removes only the owned render job, launches or polls the existing isolated transcription worker, and returns the transcript filename when complete.

The transcript receives a `timeline_source` binding containing workstation, project, timeline, timeline identity/edit fingerprint, frame range, frame rate, WAV fingerprint, and WAV duration. `create_caption_test` accepts only a transcript whose binding matches the source timeline read back immediately before duplication. Legacy media transcripts remain usable by long-form workflows but are rejected by this timeline-caption path.

Failure cleanup is ownership-bound: only the render job and temporary artifacts created by this job may be removed. The original timeline is reselected after every call, and the project is never saved.

## Success criteria

- A transcript for `video in 3.mp4` is rejected before any timeline duplicate is created.
- A transcript produced from `advbeppe / Timeline 1` is accepted only while the edit fingerprint still matches.
- The transcript text and word timestamps come from the 645-frame timeline audio, not from `WhatsApp Video 2026-.mp4` in full.
- Live read-back reports the new test timeline, caption cue count, source binding, and `saved: false`.
