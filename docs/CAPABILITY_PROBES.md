# Meta capability probes (Gate 0)

Run 2026-10-27 against `https://api.meta.ai/v1` with the key from `.env` (`META_DEV_API`, never printed).
Script: `scripts/meta_probe.py`. Raw ledger: `validation/probe_ledger.jsonl`. Project cap at probe time: $10 (run cap $2).
Costs are `usage × list price` from https://dev.meta.ai/docs/pricing-rate-limits (2026-10-27) — **estimated, not billed amounts**.
The pricing page does not document how native video is tokenized; video cost below is inferred from returned `usage`.

| Probe | Model | Input | HTTP | Latency | Usage | Est. cost | Observed semantics |
|---|---|---|---|---|---|---|---|
| Structured text | `muse-spark-1.3` (Responses, `text.format` json_schema strict, effort=low) | 1 prompt | 200 | 3.3 s | 17 in / 381 out (360 reasoning) | $0.00164 | Schema-valid JSON in `output[].content[].text`. Reasoning shares the output budget. |
| Native video | `muse-spark-1.3`, Files API upload, `input_video{file_id,fps:1}` | 60 s clip, 640×266 H.264+AAC, 2.55 MB | 200 | 22.5 s (+4.0 s upload) | 6,990 in / 1,551 out | $0.01533 | ≈117 input tokens per second of video at fps=1 and 640 px. Model shot boundaries within ~1 s of contact-sheet cuts — **model timestamps are hints only**. Est. 5-min pass at fps=1 ≈ 35k tokens ≈ $0.05. |
| SAM video, concept "blue jacket" | `sam-3.1` stream | 3 s, 640×268, no audio | 200 | 4.6 s | `video_frames_processed`=72 | $0.0144 | Zero records returned on a clip where a blue/black jacket is visible (no deltas; `output_text.done` not captured in this first run). Treat as unverified negative. Billed at native 24 fps → **downsample before SAM**. |
| SAM video, concept "person" | `sam-3.1` stream | same | 200 | 5.3 s | 72 frames | $0.0144 | 72 lines `<Nf>id<|box;x1..;w=640;h=268;c=..|><|mask;..;data=H,W,!base85|>`. Boxes are **proxy pixels**; must map to source. Text arrives in deltas and in `response.output_text.done`. |
| ASR Vietnamese | `muse-voice-transcribe-1.0`, `/asr/transcribe` ENDPOINTING, languageBias=["Vietnamese"] | 4.96 s mono 16 kHz WAV, **espeak-ng synthetic speech** | 200 | 2.6 s | audioDurationMs=4960 | $0.0002 | Exact diacritic transcript; one turn `startMs=0,endMs=4460`. Turn-level only — no word timestamps. |

Pipeline measurement (Gate 1 run `run-acf67e0ab88143719969`): frame-confirmation calls with 3 × 960 px PNG frames used 1,588–1,603 input tokens (≈ 530 per frame incl. prompt).

Probe total: **$0.04597 estimated** (5 calls). `GET /v1/models` returned HTTP 200 with an empty `data` list — model availability is established by calls, not the listing.

Not established by these probes: detector accuracy, timestamp precision, SAM recall, ASR accuracy on real Vietnamese speech, audio handling of spark-1.3 (documented caveat). A successful HTTP response is not qualification.
