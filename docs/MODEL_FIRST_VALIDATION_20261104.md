# Model-first reconstruction validation — 2026-11-04

MomoBot 0.9.0 changes interpretation and routing. Scientific algorithms are unchanged.

## Automated checks

176 unit/GUI regression checks pass on native Windows Python 3.12 / PySide6. This includes 25 new model-first/typed-contract checks. The earlier 151 checks isolate the existing deterministic executor using model_first=False; they do not claim to test the default shipping router. The new checks use the default model_first=True router and mock model packets to inspect ordering, cancellation and dispatch deterministically.

Coverage includes model invocation before parameter changes and metadata reads; HDF5-folder routing; short geometry/mode answers; relative ranges; angle-vs-center units; changed-plan confirmation; timing pilots; invalid/invented paths; no offline fixed-rule fallback; stale confirmation invalidation; and discarding late interpretations after cancellation. The native launcher self-test additionally asserts model_first_reconstruction=True.

## Real local model

The existing Gemma 4 26B-A4B QAT Q4_0 server on physical GPU 1 was used. No model was downloaded, swapped or stopped for these tests. The existing generation profile is retained. Visible activity indicates actual inference/validation and does not expose private chain-of-thought.

- Seven independent messages: literal ± and +/-, explicit interval bounds, relative doubled width, English number words, step edits and negated generation. All adopted settings matched expectations.
- Eight-turn real GUI conversation: actual HDF5 metadata, Lamino selection, signed -20 tilt, traditional mode, 807.5 ± 50 / step 1, doubled width, correction back to ±50 and explicit generation. The first seven turns dispatched no job; the last submitted a trial with the actual configured values.
- Seven further real GUI turns across two conversations: center-only automatic search with text feature, explicit auto bounds/initial step, conceptual explanation, explicit center-search start, complete known-center Lamino command, yes-but-GPU edit and final confirmation. Automatic center-only intent did not become a full reconstruction; the GPU edit required another review.

Across these 22 real-model messages, observed end-to-end times were 1.02–5.34 seconds (median 1.77 seconds), with the model already loaded. First-context calls were slower. This is a small functional sample, not a general accuracy or guaranteed-latency benchmark.

Scientific submission was mocked in both live GUI tests. There were **zero new scientific compute jobs**. The real HDF5 was read for metadata only and its size/mtime were verified unchanged. Earlier native scientific validation is documented separately; no new reconstruction-quality claims are made here.

## Release checks

The installer and portable source package require the existing Python/scientific environments, model weights and llama.cpp runtime. Private chats, Telegram configuration, runtime executables, model weights, HDF5 data and local test evidence are excluded. Production, shared-account code, public source and release source are compared by content hashes before publishing. Runtime account separation remains per-user.
