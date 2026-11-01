# Validation — 2026-10-27

This is the separate 0.2.0 conversation interface. The original 0.1.0 Assistant Lab source and launcher are preserved. SHA256 verification matched all 28 original source/document/launcher files listed in `backups/original_source_hashes.json`. Its dated source ZIP is also retained.

## Automated and local-model checks

- 27 application checks: workflow progression, file/center reset, validation before execution, atomic handling of invalid parameters, preservation of explicit rows during delayed metadata inspection, independent task drafts/history, correct routing of asynchronous replies after switching tasks, dataset-preparation continuation, selected output registries, and stopping only the selected conversation's job.
- 20 English conversation cases passed after application validation and explicit-answer binding. These include task choice, short prompt/epoch answers, all versus middle rows, automatic center choice, percentages, seed, parameter questions and unsupported-operation refusals.
- This is **application-assisted interpretation**, not a claim that raw Qwen independently got every parameter correct. Earlier raw responses confused row ranges with center-search ranges and sometimes omitted an explicit percentage. The application now binds recognized short answers to the same choices as the buttons and verifies explicit numeric fields. Original model responses and normalization notices remain logged locally.

The local-model command cases used GPU 1 for speed. The actual GUI-to-backend trials used CPU Qwen, matching the default interface.

## Actual chat workflow checks

Nine free-text turns completed the expected guided steps. File selection was exercised through the same file-chooser callbacks, using known test paths. These trials also checked that explaining an epoch leaves the entered two-epoch training configuration unchanged and does not start training.

| Actual task | Scope | Worker elapsed |
|---|---|---:|
| Reconstruction | NMC811_Rod, FourierRec, GPU 1, center 1028.75, rows [1023,1025) | 19.19 s |
| Segmentation | One original sample_2 image, prompt particle, confidence 0.25 | 39.16 s |
| Training dialog | Existing saved training dataset, two epochs, batch one, plus an explanation question | Reached review; intentionally not submitted |

The reconstruction produced two finite, nonconstant TIFF slices. Segmentation produced its label TIFF, instance NPZ, CSV and timing files. Both ran from this chat interface and reported completion from worker status, not from the language model's reply.

A full new training/convert run was not repeated for the new frontend. The reused backend had already completed a one-epoch train, saved a 9.389 GiB full checkpoint, converted a 3.213 GiB inference checkpoint and successfully segmented an image in Assistant Lab. The new preparation-to-training conversation transition is separately covered by the application tests. Full-volume benchmarks, training quality, laminography and all reconstruction methods are outside these small frontend trials.

## Where results are stored

- `test_outputs_unit_final.log`
- `test_outputs/chat_model_cases.json`
- `test_outputs_model_bound.log`
- `test_outputs_live_final.log`
- `test_outputs/live_1793144377533543100/report.json`
- Screenshots and scientific outputs under that live-test folder.
- `test_outputs/original_source_verification.json`

The task list includes the two completed real validation conversations, clearly named **Test**. A fresh **New task** opens by default. These records can be inspected without rerunning the jobs.

## Permission boundary

The language model only returns a restricted plan and a reply. File dialogs or explicitly supplied paths select inputs; jobs write to new task folders. No arbitrary-command or delete-source tool is available to Qwen. The Windows application itself has the current user's access rights and has no OS-level directory sandbox. Training additionally creates its own uniquely named runtime YAML under the existing SAM3 repository. This distinction is explained in the interface's permissions menu.
