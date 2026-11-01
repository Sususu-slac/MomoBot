# MomoBot 0.6.0

## Windows source package

This release is a workstation GUI and Windows launcher bundle. Models, llama.cpp
binaries, scientific backends, datasets and saved conversations are external.

1. Clone/download this repository to `D:\BL62_Assistant_Chat`.
2. Create/use the Windows Python 3.12 environment `BL62_Studio`, then run
   `python -m pip install -r requirements.txt` inside that environment.
3. Install the companion [Reconstruction](https://github.com/Sususu-slac/BL62_Reconstruction_GUI)
   and [Fine-tune](https://github.com/Sususu-slac/BL62_Finetune_GUI) projects and
   their native/WSL scientific environments before running scientific tasks.
4. `python tools/install_momobot_runtime.py` downloads the pinned local llama.cpp
   Windows runtime. The model is external; `tools/download_momobot_parallel.py`
   is the resumable, checksum-verified downloader used on the original workstation.
   Create `D:\Chcekpoints\LLM` before using it. The primary model is about 19 GB.
5. Review the workstation paths in `assistant_lab/config.py` (companion projects,
   Conda environments, shared SAM3 checkpoint and language models). The supplied
   defaults describe the original Windows/WSL workstation.
6. Run `run_gui.bat`, or run `python app.py` from the project folder. Optional
   `create_shortcut.ps1` creates the kitten desktop shortcut for that layout.

Model downloads require network access; ongoing inference runs locally. Optional
Telegram access is configured from Settings. Store credentials only through that
local setup; do not commit `telegram.json`, `settings.json`, conversation or output
directories. These are excluded from this repository and release archives.

## Light / Dark

Use the upper-right **Switch to Light** / **Switch to Dark** button. Each GUI
remembers its own choice; new installations default to Dark. Light uses blue
buttons and selected controls, while Dark keeps the original green accents.
Dialogs, menus, logs, charts and progress bars follow the theme. Images, masks,
annotation edits, histogram settings, training state and chat drafts are preserved.

See [theme validation](THEME_VALIDATION_20261101.md) for the checks and their scope.


<img src="assets/momobot-orange-kitten.png" alt="MomoBot chubby orange kitten" width="96">

MomoBot uses a chubby orange baby kitten app/desktop icon. Standalone Hi, Hello and Chinese greetings include the matching Hi! sticker in chat; Telegram mirrors it as a native sticker. Greeting replies remain local and do not wait for model inference. See assets/ORANGE_GENERATION.md for the current artwork and prompts; assets/GENERATION.md documents the earlier white kitten.

## Local model and GPU assignment

The default language model is **Qwen3.8-27B Q4_K_M**, running on **physical GPU 1** with an 8K context and thinking disabled for ordinary requests. Opening MomoBot loads the model; keeping the window open or minimized keeps it resident. Closing MomoBot stops its model process and releases its GPU memory. Scientific jobs continue in their own processes. A cold model load measured about 35 seconds; greetings still reply immediately while it loads.

New scientific tasks default to **GPU 0**, including reconstruction, SAM3 segmentation and fine-tuning. Existing archived job records retain their actual GPU. Task GPU remains configurable. The language model's CUDA visibility is isolated to its own process.

Use **Settings → Language model…** to switch between the primary GPU model and the retained **Qwen3-4B CPU fallback**. The new llama.cpp b11988 runtime is local to `runtime/llama-b11988`; scientific environments are reused. The primary model is stored at `D:\Chcekpoints\LLM\Qwen3.8-27B-Q4_K_M.gguf` and its published SHA256 was verified. See VALIDATION_0.5.0.md for measurements and test limits.

Pasted `file:///D:/…` links are normalized into Windows paths, including URL-encoded spaces. Current paths need not be repeated in follow-ups. Unrequested output/checkpoint changes are ignored, proposed source paths must match explicit input, and a newly selected dataset starts with its own center. Full-volume row limits are computed from inspected data. Saved centers are restored only for the matching input dataset.

## Chat from Anywhere

Open **Settings → Chat from Anywhere…**. The setup remains available there after pairing.

1. **Connect Telegram:** paste your bot token and click **Connect**. If you need a token, expand **How do I get a token?** for phone instructions and a BotFather QR code. Create the bot once in Telegram with `/newbot`. The token is saved encrypted for the current Windows account; it is not stored in conversation history.
2. **Scan with your phone:** connection success automatically shows a pairing QR code. Scan it with your phone camera, open Telegram and tap **Start**. The pairing code is included in the link; there is nothing to type. It expires after ten minutes and the displayed QR code refreshes automatically. The first valid pairing binds one private Telegram account. Other users and group chats cannot execute tasks.

After pairing, the dialog displays **Phone connected** and closes automatically. Reopen it to view connection status or disconnect. Advanced options contain link-copying and phone-unpairing controls. The first screen shows only the token field, Paste token, Connect, optional help and Close.

Chat with MomoBot normally. `/tasks` lists desktop tasks; copy `/use TASK_ID` to select one. `/new` creates a task, `/status` reads actual progress, `/stop` safely stops it, `/curve` and `/image` send saved center-search artifacts. The current task is initially the desktop's selected task. Remote task selection preserves the desktop selection and unsent draft. Replies and final results are mirrored for subscribed tasks; temporary Working status is replaced when a reply or job finishes.

The computer and MomoBot must stay running and online. Desktop startup reconnects a previously enabled Telegram connection. Offline commands from before application startup are ignored rather than executed later. While the model is processing another request, additional task messages are rejected with a retry notice; they are not queued. Text requests and computer-local data paths are supported. File uploads and voice are not supported. Messages and explicitly requested result images travel through Telegram; model inference and scientific work stay on the computer. No inbound port or public web server is opened. **Disconnect** pauses remote access; **Disconnect and unpair phone** removes the account binding.

Setup uses the official [Telegram Bot API](https://core.telegram.org/bots/api#getupdates) and [bot deep links](https://core.telegram.org/bots/features#deep-linking). Automated validation decodes the generated QR code and uses simulated Telegram requests; a real phone must still complete pairing to verify actual mobile delivery.

## Chat operation

Describe a task and paste its path. The assistant checks the data and supplies ordinary defaults. Direct task requests run after required inputs are available; discussion questions do not run jobs. Missing information is requested in chat. There are no task-selection, parameter-step or Start buttons. Type `start`, `stop`, a follow-up question, or a new request. English and Chinese task requests are supported; the interface remains English. The optional + attachment button remains available.

Standalone greetings, thanks, name questions and general capability questions receive immediate local replies without waiting for Qwen inference. Messages that include a task, path or parameter still use the task handling flow.

Messages are appended without rebuilding existing message widgets. Scrolling through history preserves the reading position. While a request is being handled, one short status beneath the reply shows the current action (or “Working…”). It disappears when that step finishes. There is no progress bar or displayed reasoning transcript.

Manual trial searches use a single detector row and return candidate images for the user to compare. They do not select a best center or angle. Automatic SAM3 center search asks which feature to recognize. A center-only request returns its result and waits; a request to find a center and reconstruct uses the existing analysis pipeline. Automatic angle scoring is not implemented; manual lamino-angle trials use the existing LineRec backend.

Follow-up questions read saved job results: computed center, slice, elapsed time, scoring method, artifacts and output paths. Ask to open the curve or best image. Computed centers are distinguished from manually entered centers; the unset setting 0 is never used as a search result. Saved results are restored on reopening, and explicit user confirmations are recorded.

## Preserved versions and runtime

The original Assistant Lab remains unchanged. Dated source/conversation backups are stored under backups, including the version before the Qwen3.8 upgrade. The desktop shortcut MomoBot opens this version; its project folder remains D:\BL62_Assistant_Chat. The shared SAM3 checkpoint and Windows/WSL scientific environments are reused. Keep D:\BL62_Assistant_Lab\runtime for the original Lab; MomoBot 0.5 uses its own runtime. Desktop operation requires no cloud account; optional remote access requires Telegram.

## Permissions

The local model proposes a bounded plan. The application implements only selected scientific operations, task progress, result lookup, stopping owned workers, and opening local result artifacts. It has no arbitrary command, delete-source, software-installation or web-browsing tool. Inputs are read and each execution writes to a new task directory. A direct request in chat authorizes its execution; questions do not. The application still uses the current Windows account and has no OS-level directory sandbox.

## Validation

See VALIDATION_0.5.0.md for the model/GPU/path changes, VALIDATION_0.4.0.md for Telegram integration, and VALIDATION_0.3.0.md for underlying scientific workflows. Earlier reports are retained as historical evidence.

---

## Previous 0.2.0 documentation

# BL62 Assistant Chat — Simple, 0.2.0

A separate conversation-first GUI. The original **BL62 Assistant Lab** remains in its original folder and has a dated source backup under `backups/`.

The left side lists saved tasks. The right side contains their conversation, contextual choices, actual progress and bottom message composer. New tasks offer reconstruction, segmentation, fine-tuning, dataset preparation and rotation-center search. The application loads local Qwen automatically on CPU. File selection uses the **+** button or the current question's file chooser. Double-click a task to rename it.

## Workflow

1. Choose a task or describe it in English.
2. Follow the conversation to select input data and answer the required questions.
3. Review the effective settings in chat. Select **Start**, or type `start` when the review is ready.
4. The task runs in the background; the conversation shows actual progress and output paths. You may switch conversations or prepare another task while it runs. Scientific jobs run one at a time in this version.

Shift + Enter inserts a line break. The **…** menu contains Task GPU, model reload, task logs, results and an access-permissions explanation. Other supported parameters can be changed in chat. Known short answers and explicit numeric parameters are checked by the application; the LLM handles interpretation and conversational explanations. It does not determine job completion.

Reconstruction asks whether to use a known center or find one automatically, then asks for the row range. A new data file clears the previous file's center. End row is exclusive. Automatic center search supports tomography only. It uses the existing confidence-weighted SAM3 search. Automatic angle search is not implemented.

Segmentation asks for the image folder, SAM3 text prompt and image limit. Labels are saved to a new output folder. Fine-tuning accepts an exported training/validation dataset or raw COCO data; raw COCO data is prepared first, then the conversation continues to training settings. The saved dataset path is passed to training automatically. Training uses the existing WSL environment and automatically converts its full checkpoint after completion. The existing full training/convert workflow was verified in Assistant Lab; this frontend's validation exercises training setup and the prepare-to-train transition without repeating a long training run.

All conversations persist under `conversations/`. New task outputs default to `outputs/jobs/`; another output parent can be selected in the final review. The original Lab's task history is preserved separately. This version keeps its own task list, model process and worker records.

## Model and dependencies

- Shared model: `D:\Chcekpoints\LLM\Qwen3-4B-Instruct-2507-Q4_K_M.gguf`.
- Shared SAM3 checkpoint: `D:\Chcekpoints\checkpoint_demo_05142026.pt`.
- llama.cpp binaries reused from `D:\BL62_Assistant_Lab\runtime`; keep this folder.
- GUI: existing Windows `BL62_Studio` Python environment.
- Reconstruction, SAM3 and training: the same native/WSL environments and libraries as Assistant Lab.

No model download is repeated. The two interfaces can remain installed together. This is a workstation prototype, not a portable installer.

## Access permissions

Qwen receives the selected task context and recent conversation. It returns a bounded JSON plan and a conversational reply. The application implements a fixed set of operations: inspect selected inputs, reconstruct, find a center, segment, prepare a dataset, train, show progress, stop its own workers and open results. There is no general command execution, source-deletion, software-installation or web-browsing tool exposed to Qwen. The model server listens on localhost and needs no cloud account.

The application runs with the current Windows user's permissions. It does **not** provide an operating-system filesystem sandbox. Its limits are enforced in the application: explicit input paths, new output folders and a Start action before scientific execution. Existing scientific source data and production checkpoints are read as inputs. Training writes its uniquely named runtime configuration into the existing SAM3 repository. Logs and task conversations are saved locally.

## Validation

See `VALIDATION.md`. Automated tests cover conversation isolation, task switching during asynchronous responses, source validation, late metadata checks, cancellation routing, explicit choices and the preparation-to-training transition. Actual small reconstruction and segmentation jobs were run from the chat interface with CPU Qwen. Model-response raw text and application normalizations are recorded separately under `outputs/`.
