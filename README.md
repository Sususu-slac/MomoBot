# MomoBot 0.8.1

A local chat assistant for BL62 reconstruction, SAM3 segmentation and fine-tuning. The left side lists tasks; the right side contains the conversation and message composer. Standalone greetings reply immediately with the orange kitten sticker. Light/Dark themes are available.

## Windows setup

Install the Windows launcher package or extract the portable source ZIP. The existing BL62_Studio Python 3.12 environment is required; the launcher package does not bundle Python, model weights or scientific environments. Prepare dependencies with `python -m pip install -r requirements.txt` in that environment.

MomoBot currently configures **Google Gemma 4 26B-A4B QAT Q4_0** as its only local language model, on physical GPU 1. The previously removed Qwen profile is not restored. Scientific jobs default to GPU 0. Download the configured model with `python tools/download_model.py --model gemma4`; weights and llama.cpp runtime remain external. See `model_catalog.json` for the pinned model revision and checksum. Closing the chat window stops its own model server; independent scientific workers retain their own lifecycle.

Reconstruction requires the current **BL62 Reconstruction 1.2.6 or newer** source/backend and its native reconstruction/SAM3 environments. Fine-tuning also requires the existing training tools and a WSL distribution/environment registered for the Windows account running the training.

## Reconstruction by chat

Paste an HDF5 path. MomoBot reports its metadata, asks for Tomo/Lamino geometry if unspecified, then guides traditional trial selection or automatic Text/Instance center search. Laminography needs its signed acquisition tilt angle. Theta alone does not distinguish these geometries.

Traditional trials create numbered previews and open their folder. Choose by number, parameter value or saved filename. A full reconstruction plan is shown before one confirmation starts it. A complete explicit command skips redundant questions. Only find center saves the result and waits; a later instruction can reconstruct with that center. Segment All can be included explicitly in the plan.

Changing an input or rejecting an edit invalidates confirmation. Cancel, Safe Stop, retry and restart preserve task boundaries and partial outputs. Result queries read saved jobs for the current input. After reconstruction, segment these results creates a separate task using the saved output folder.

See [the SOP guide](docs/RECONSTRUCTION_SOP.md) and [validation scope](docs/SOP_VALIDATION_20261104.md). 148 regression/GUI checks and four small native scientific workflows passed before deployment. These are functional checks, not a new reconstruction-quality or language-model benchmark.

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
