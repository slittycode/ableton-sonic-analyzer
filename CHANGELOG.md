# Changelog

All notable changes to `sonic-analyzer-UI` are documented here in reverse chronological order.

## Unreleased

- Added the Phase 1 MIDI transcription toggle and wired it through the backend request as `transcribe=true|false`.
- Added the Session Musician polyphonic and monophonic source toggle when both `transcriptionDetail` and `melodyDetail` are present.
- Tightened the Phase 2 prompt around 8-device minimum mix chains and protected group compaction.
- Fixed the estimate and status panel labels to render seconds with a lowercase `s`.

## v0.3.0

- Added `transcriptionDetail` parsing and typing across the frontend.
- Added the Session Musician panel for polyphonic transcription workflows.
- Added the Phase 1 estimate status panel and estimate smoke coverage.
- Expanded the diagnostic log and request-phase labeling.
- Added favicon and React Strict Mode coverage.

## v0.2.0

- Split backend communication into a dedicated Phase 1 client and a dedicated Gemini Phase 2 client.
- Added explicit environment handling through `src/config.ts` and `src/vite-env.d.ts`.
- Added mocked smoke tests plus unit tests for the backend client and UI flows.
- Updated the frontend schema expectations for arrangement overview, mix-chain output, sonic element fields, BPM rounding, and the spectral-balance note.

## Pre-v0.2.0

- Repository bootstrap and initial Ableton reconstruction UI work predate the first tagged release in this repo.
