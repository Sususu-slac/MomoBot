# MomoBot local model comparison — 2026-11-02

The same 25 valid synthetic commands were evaluated twice on physical GPU 1 (RTX 6000 Ada, 48GB) with 8192 context, seed 42 and temperature 0. Input tasks, schemas and application validation were held fixed for each comparison phase. Qwen uses the existing completion adapter. Other models use native chat templates; Muse uses low reasoning and a larger output budget, while Gemma/Nemotron disable thinking.

|Configuration|Instruction checks passed|Mean complete reply|Incremental VRAM|
|---|---:|---:|---:|
|Qwen3.8-27B (final application)|50/50|4.04 s|18.2 GiB|
|Gemma 4 26B-A4B (final application)|50/50|1.32 s|14.3 GiB|
|Muse Glimmer 30B (initial native adapter)|48/50|8.41 s|18.3 GiB|
|Nemotron 3.5 Lightning (compatibility retry)|40/50|1.01 s|17.8 GiB|

These are checks of MomoBot task classification, requested parameters/control fields, source-path grounding and synthetic saved-result answers, not a general intelligence benchmark or the success rate of actual scientific computation. Native adapters and reasoning budgets differ. Download/build I/O was present during some runs, so treat response times as observed desktop measurements, not an isolated hardware benchmark. Cold model-load times are not ranked.

Gemma initially passed 46/50. The application was then corrected to bind a user’s literal “middle slice” selection independently of model numeric spelling, and to reject unsupported original-file deletion and automatic tilt-angle scoring before dispatch. With these same application checks, final Gemma and Qwen each passed 50/50. This improvement includes deterministic application logic and must not be interpreted as raw-model accuracy.

Muse passed 48/50 but missed follow-up reconstruction requests and was slower. Nemotron initially failed structured output with a runtime grammar exception; changing the forced end-of-thinking configuration made it runnable, after which it passed 40/50. The initial exception is a compatibility failure, not a model-accuracy score. Neither model is included in the recommended two-profile selector.

The final Gemma and Qwen profiles were also loaded and switched through the actual GUI, and each produced the correct dispatch parameters for a tiny HDF5 reconstruction request. Dispatch was intercepted: no reconstruction, SAM3 inference or fine-tuning backend was launched for these language-model tests. Production conversations and Telegram messages were not used or sent. Default scientific jobs stay on GPU 0.

All downloaded weights were validated against pinned Hugging Face revisions, byte lengths and SHA256 checksums. See `model_catalog.json` for the retained models. Model weights and private test logs are excluded from this repository and its Windows releases.
