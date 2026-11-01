# Conversation frontend validation — 0.3.0, 2026-10-27

38 application checks pass. They cover independent conversations, asynchronous task switching, stable history position and reused message widgets, progress attached to the correct reply, explicit execution versus discussion, source and geometry validation, automatic feature questions, center-only versus reconstruction routing, manual trial routing, result queries without job execution, and the regression where a saved center was confused with an unset zero.

The actual chat trials pasted file paths into the composer and used CPU Qwen. No task-type, parameter-choice or Start button was used.

| Actual job | Verified scope | Worker elapsed |
|---|---|---:|
| Reconstruction | Cropped exchange HDF5, rows [63,65), center 64, two finite TIFF slices | 11.03 s |
| Manual center trial | One detector row, two candidate reconstructions, no automatic scoring | 10.84 s |
| Manual lamino-angle trial | One row, fixed center 64, two finite angle candidates, existing LineRec backend | 16.88 s |
| Chinese segmentation request | Pasted folder path, first image only, particle, confidence 0.25 | 34.97 s |
| Automatic center only | NMC811_Rod, search [1027,1030], prompt explicitly requested then supplied, target step 0.25 | 80.64 s |

The automatic-center trial produced a saved center and did not reconstruct the volume. A subsequent chat question retrieved the actual saved value without another job. A discussion request with a file path also remained unexecuted. Center-search-plus-all-rows routing is covered separately with the worker launch mocked; the underlying analysis pipeline had already been run in earlier integration tests.

The manual trial tests used a small cropped scientific HDF5 to check execution, candidate count and finite output. They do not validate a physical laminography angle for the original tomography dataset. Full-volume speed and scientific optimality are not established by these frontend tests. Training was not repeated; its existing backend and dataset-to-training path are reused.

The first monitor encountered a Windows console encoding error after submitting the Chinese segmentation test. The scientific worker completed successfully; its output and requested one-image / 25% parameters were recovered and checked by the continuation monitor. This was a test-console issue, not a failed segmentation job.

Result-lookup regression: the user's existing analyze job 20261027_171855_3298bd4f_analyze saved center 1017.0, seven rounds, 197 candidate evaluations, detector row 1023, five reconstructed slices and total elapsed 368.766 seconds. The old frontend incorrectly answered using setting center=0. Current lookup reads those saved artifacts, reports 1017, distinguishes algorithm results from entered values, and restores the result into the conversation's working settings.

Evidence:

- test_outputs_unit_v030.log
- test_outputs_live030_final.log
- test_outputs_live030_remaining.log
- test_outputs/chat030_1793148003696497100/report.json
- Screenshots, copied inputs and scientific outputs under that test folder.

The 28 original Assistant Lab source/document/launcher hashes still match their preservation manifest. Version 0.2.0 is archived under backups/chat_0.2.0_20261027_172239.zip. Production GUI sources and the unified SAM3 checkpoint were not replaced.
