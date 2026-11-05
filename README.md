# MomoBot 0.9.1

A local chat assistant for BL62 reconstruction, SAM3 segmentation and fine-tuning. The left side lists saved tasks; the right side contains the conversation and message composer. Each launch opens a fresh chat. Sending the first message creates a task automatically; the New task button remains available. Select a saved task to reopen its conversation and draft. Standalone greetings reply immediately with the orange kitten sticker. Light/Dark themes are available.

## Windows setup

Install the Windows launcher package or extract the portable source ZIP. The existing BL62_Studio Python 3.12 environment is required; the launcher package does not bundle Python, model weights or scientific environments. Prepare dependencies with `python -m pip install -r requirements.txt` in that environment.

MomoBot currently configures **Google Gemma 4 26B-A4B QAT Q4_0** as its only local language model, on physical GPU 1. The previously removed Qwen profile is not restored. Scientific jobs default to GPU 0. Download the configured model with `python tools/download_model.py --model gemma4`; weights and llama.cpp runtime remain external. See `model_catalog.json` for the pinned model revision and checksum. Closing the chat window stops its own model server; independent scientific workers retain their own lifecycle.

Reconstruction requires the current **BL62 Reconstruction 1.2.6 or newer** source/backend and its native reconstruction/SAM3 environments. Fine-tuning also requires the existing training tools and a WSL distribution/environment registered for the Windows account running the training.

## Reconstruction by chat

Paste an HDF5 path. MomoBot reports its metadata, asks for Tomo/Lamino geometry if unspecified, then guides traditional trial selection or automatic Text/Instance center search. Laminography needs its signed acquisition tilt angle. Theta alone does not distinguish these geometries.

Traditional trials create numbered previews and open their folder. Choose by number, parameter value or saved filename. A full reconstruction plan is shown before one confirmation starts it. A complete explicit command skips redundant questions. Only find center saves the result and waits; a later instruction can reconstruct with that center. Segment All can be included explicitly in the plan.

Changing an input or rejecting an edit invalidates confirmation. Cancel, Safe Stop, retry and restart preserve task boundaries and partial outputs. Result queries read saved jobs for the current input. After reconstruction, segment these results creates a separate task using the saved output folder.

Every accepted reconstruction turn goes to the local Gemma model first, including short geometry/mode answers, parameter corrections, confirmations and result questions. A typed interpretation is validated before the reconstruction SOP applies it. An unavailable model or invalid interpretation cannot silently fall back to a fixed reply or an old parameter value. Greetings remain immediate; emergency cancellation while an interpretation is pending takes priority.

See [the SOP guide](docs/RECONSTRUCTION_SOP.md), [model-first validation](docs/MODEL_FIRST_VALIDATION_20261104.md) and [earlier scientific validation](docs/SOP_VALIDATION_20261104.md). Functional testing does not establish reconstruction quality or general language-model accuracy.

## Phone access

Open **Settings → Chat from Anywhere…** on the desktop. Enter the Telegram bot token, connect and follow the pairing instructions. Only the paired owner can send supported tasks. Remote example prompting needs image and binary-mask paths accessible on the computer; interactive painting uses the desktop editor. Keep Telegram tokens and conversation files private.

## Paths, shared accounts and access

- `MOMOBOT_STATE_ROOT`: per-user conversations, preferences, Telegram settings and logs.
- `MOMOBOT_RUNTIME_ROOT`: llama.cpp executable directory.
- `BL62_MODEL_DIR`: shared model directory, default `D:\Chcekpoints\LLM`.
- `BL62_CONDA_ENVS`: shared scientific Python environments.
- `BL62_RECON_ROOT`: reconstruction source/backend directory, default `D:\BL62_Reconstruction_GUI`.

The launcher preserves an established source folder’s chats; new installs use the current account’s local BL62_UserData folder. Code/models can be shared while each account retains its own state. Reopen MomoBot after a source update.

The assistant arranges a fixed set of scientific tasks; model text is not arbitrary executable code. It has no general shell, source-file deletion, software-installation or web-browsing tool. Workers run with the current Windows account’s filesystem access; this is not an operating-system folder sandbox. Delete task removes the saved chat/task entry and preserves source data and generated results.

## Development

Run `python -m unittest discover -s tests -p "test_*.py"`. SOP tests need the reconstruction metadata/exemplar source; set BL62_RECON_ROOT accordingly. GPU integration checks are documented separately. Model files, user state and datasets are excluded from the repository and releases.

## 0.8.2 — reconstruction introduction

A new reconstruction request first explains Traditional and Smart (Text/Instance) workflows, then asks for the data when missing. Providing a path reads and displays HDF5 information before asking for geometry. The introduction is shown once per workflow. The window title now displays the running version. 151 regression/GUI checks passed; the exact quoted nmc_32_113.h5 command returned metadata and asked for geometry without launching computation.

## 0.9.0 — model-first reconstruction messages

Gemma interprets each reconstruction message before the application checks paths, units, dimensions and workflow state. For example, `please 807.5 ± 50 px, step 1` updates the candidate range to **757.5–857.5**, step **1**, without starting computation. Relative changes such as `make it twice as wide` also use the current settings. Explicit generation/search commands and reviewed-plan confirmation remain distinct from configuration.

The UI shows genuine model activity while waiting and removes the activity when complete. Actual execution parameters are echoed from validated settings. Failed interpretations invalidate stale confirmations; cancellation discards late model updates. Model text cannot execute arbitrary commands or establish scientific results. Existing reconstruction/scoring algorithms and the GPU assignment (Gemma GPU 1, scientific defaults GPU 0) are retained.

## 0.9.1 — fresh chat and reliable scrolling

Startup lists saved tasks without opening a previous conversation or creating an unused empty task. Type directly and send to create a task, or use New task explicitly. Attachments also work from the fresh page; cancelling a picker leaves it empty. History, drafts and running workers remain available independently.

Chat follows new messages, growing replies and delayed text wrapping. Scrolling up pauses following so history stays readable; sending your next message resumes following the latest messages. Switching tasks restores the saved reading position. Model-first reconstruction behavior is unchanged.
