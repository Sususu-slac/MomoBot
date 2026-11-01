# MomoBot 0.5.0 validation — 2026-10-29

## Installed configuration

- Qwen3.8-27B Q4_K_M, 8K context, no-thinking mode, physical GPU 1.
- Scientific task default GPU 0; archived job settings remain factual. Model CUDA visibility is set only in its subprocess, not in the GUI/worker environment.
- Model path: D:\Chcekpoints\LLM\Qwen3.8-27B-Q4_K_M.gguf.
- Model bytes: 18973870528; pinned revision: a316ea527fde32c12487be7574e2db5ac2ad2a7e.
- Published model SHA256 verified: c600de0300ae8a0eb3a6c0b8b5561b8b96f16bd2c863c2a66c42de29d391a747.
- Independent native Windows llama.cpp build b11988 (commit abb76ab38), CUDA 12.4 and CPU runtimes. Archives came from the pinned ggml-org release and were hashed; installation records are in runtime/llama-b11988/verified.json.
- Retained Qwen3-4B-Instruct-2507 Q4_K_M as the selectable CPU fallback. Settings → Language model controls selection and restarting owned inference processes.
- Prior source and conversations are backed up in backups/before_qwen38_20261029_145751.zip. Other scientific GUI/environment sources were not modified.

## Native checks

78 automated checks passed in 15.240 seconds. Covers the existing conversational/Telegram/sticker workflows plus file-URI normalization, URL-encoded spaces, exact source-path grounding, ignoring unrequested output/checkpoint updates, explicit numeric bindings, source-specific center recovery, all-slice limits, GPU process isolation, and immediate greetings while a model is loading without undoing cancellation.

Ten real primary-model routing cases passed: original file link, center-only search, center-and-full-volume analysis, manual center candidates, manual angle candidates, segmentation, training setup, discussion-only, explicit parameters, and stop. These model interpretation cases do not execute scientific work.

A real-model test exposed a possible 0-to-0 row placeholder for “all slices”. The program now ignores unrequested row coordinates and computes full limits from data metadata. Final real-model rechecks validated paths and all typed settings for the file-link, full-volume and explicit-row requests. A GUI dry run inspected the actual NMC622_Rod5 data (901 projections, 2048 rows, width 2048), routed center search plus reconstruction to analyze, and generated rows [0, 2048), GPU 0. Worker submission was intercepted for this full-volume test; the full dataset was not reconstructed.

## Measured latency

| Request | Retained 4B on CPU | New 27B on GPU 1 |
|---|---:|---:|
| Original file-URL request | 20.855 s | 5.021 s |
| Segmentation request | 11.476 s | 6.444 s |
| Explicit center/rows/GPU | 13.811 s | 7.100 s |

The two columns compare complete deployment configurations, not models on identical hardware. These are individual sample measurements, not guaranteed production latency or a broad accuracy benchmark. The primary's ten sample responses ranged from 2.162 to 7.398 seconds. The final rechecks measured 5.052, 4.627, 7.087 seconds.

Cold model readiness: 35.395 seconds. Warm validation reload: 21.966 seconds. Standalone greetings use local responses and do not wait for inference, including during loading.

## Physical GPU memory and executed scientific test

Before load: GPU 0 11664 MiB, GPU 1 76 MiB. Loaded: GPU 0 11664 MiB, GPU 1 18674 MiB. Model residency increased physical GPU 1 by 18598 MiB (about 18.16 GiB), while GPU 0's allocation stayed unchanged at the load measurement.

With the language model resident on GPU 1, the GUI submitted a real small reconstruction to GPU 0. Its copied/cropped HDF5 input produced exactly two 128×128 TIFF slices; all values were finite and each image was nonconstant. Job 20261029_151328_9e85344d_reconstruct: succeeded, 24.875 seconds. This checks dispatch and coexistence, not full-dataset reconstruction quality.

After stopping the validation model, GPU 1 returned to 76 MiB (the pre-load baseline). Closing the production GUI uses the same owned-process shutdown path.

## Artifacts and limits

- test_outputs/qwen38_1793311860407842900/report.json — original model comparison, physical GPU snapshots and actual reconstruction job.
- test_outputs/qwen38_1793311860407842900/final_recheck.json — final model/typed-plan rechecks and full-volume GUI dry run.
- The original error command was not replayed as a full scientific job. The source was inspected read-only.
- New dataset selection clears inherited center values. A legacy failed file-URL input is repaired on startup, without deleting conversation history or starting a job. Saved centers are restored only when their recorded source matches the selected input, and do not overwrite a manually set positive center.
- Full training and full-volume segmentation were not repeated; their existing backend adapters remain in use, with GPU 0 checked as the default and explicit GPU settings forwarded as before. Real Telegram phone delivery is separate from these tests.

## Production startup confirmation

The desktop shortcut was reopened with the primary profile selected. A native Windows process check confirmed exactly one llama-server child owned by the visible MomoBot GUI, and NVIDIA's compute-process UUID mapped that child to physical GPU 1. Its startup log confirmed Qwen3.8-27B, 8192 context, loaded and listening. The final launcher uses the current --reasoning off / --reasoning-budget 0 / --no-reasoning-preserve options; 14 targeted upgrade checks also passed after that launcher adjustment (0.106 seconds). No reasoning-preservation warning was present on the final production startup. See test_outputs/qwen38_1793311860407842900/production_startup.json.

The previously failed NMC622_Rod5 file URL was repaired to a canonical Windows path in the saved conversation, and its inherited center was reset to unset. This did not start a full-volume scientific job. The user may resend the reconstruction request; automatic center scoring will still ask which feature to recognize.
