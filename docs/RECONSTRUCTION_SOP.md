# Reconstruction chat workflow — MomoBot 0.10.1

Each launch starts on a fresh chat page. Type and send to create a task automatically, use New task explicitly, or select a saved task from the sidebar. History and drafts remain saved.

Paste an HDF5 file path or a folder containing HDF5 files. MomoBot reads projection count, detector dimensions, dtype, file size, theta range and flat/dark shapes before planning computation. If a folder contains several files, choose one by its displayed number. Unquoted Windows HDF5 paths containing spaces are supported.

Specify Tomography or Laminography. MomoBot asks when geometry is unspecified: both acquisitions may contain theta, so theta alone cannot select the geometry. Laminography needs the signed, nonzero acquisition tilt angle; negative angles are preserved. Flat/dark correction must match the acquisition. This chat workflow currently uses the input HDF5’s flat/dark frames; a request for a separate external flat file is explicitly rejected rather than interpreting it as another input.

## Understanding before execution

Each accepted reconstruction message is interpreted by the local Gemma model before the SOP handles it. This includes a bare path, short answers, edits, candidate choices, result questions and confirmation. The model supplies typed intent/settings; application checks enforce supported actions, provided paths, units, finite values, detector limits, current state and confirmation. No model-ready/understanding failure silently reuses a prior default or bypasses the model. The visible activity describes model understanding and validation, not private reasoning.

A standalone greeting remains immediate. During a pending model/metadata call, cancellation and brief status controls respond directly so the user can stop or inspect the pending request. Additional computation requests are not silently queued. Once the call finishes, late cancelled interpretations are discarded. The desktop Safe Stop button directly targets the selected scientific worker.

For example, `please 807.5 ± 50 px, step 1` means center 807.5, half-width 50, range 757.5–857.5, step 1. It only changes settings. `Generate candidates` explicitly starts the configured trial stage. If a parameter remains ambiguous, MomoBot asks instead of claiming an old setting was changed.

## Linked desktop viewers

The HDF5 metadata message includes View data / Set parameters. Open it to browse projections/flat/dark and set parameters; click a projection to pick the search/trial row. Apply to Momo validates the edits and returns to the chat workflow for review. Source pixels are read-only.

Trial completion includes Review trial images / Select parameter. Choose the exact saved candidate and use its center or angle; Momo then shows the full-run confirmation. Browse reconstruction opens the saved slice stack, including available slices while a worker is still running. The viewers are nonmodal and remain bound to their originating task. Opening older conversations adds links where saved job metadata is available. These are desktop tools, not phone-hosted web pages.

## Traditional reconstruction

Ask for manual/traditional reconstruction. MomoBot offers a trial center range, step and middle detector row. The range is a starting proposal, not a measured center. You can change it before saying generate candidates. Angle trials instead require a fixed center and a tilt range. Automatic angle scoring is not implemented. ASTRA full reconstruction can use FourierRec trial images while retaining the selected full method.

After the sweep finishes, a viewer link appears. The result folder also contains numbered PNG previews and candidate_index.csv. Numbering is one-based and follows numeric parameter order. Choose by image number, ordinal, center/angle value or actual saved filename. Ambiguous numbers and multiple choices cause a clarification. MomoBot never guesses which image looks sharpest.

A selected center or angle produces a full reconstruction review, not immediate execution. The review contains source, geometry/tilt, method, center, GPU, row range, binning, expected TIFF size, preprocessing, output parent and estimated time. Output goes into a new task directory. Confirm once to execute. A complete explicit command skips questions for values already supplied and still requires that one confirmation. Edits invalidate the prior confirmation.

## Automatic center search

Choose automatic center search, then name the feature, such as particle. For an instance example, say instance and select an image; paint the mask in the existing reconstruction editor. Reference images can differ from the reconstructed candidate images. On Telegram, provide the example image and binary-mask paths on the computer, or use text prompting. Cancelling the editor permits switching back to text.

Only find center means only search: the center is saved and MomoBot waits. A subsequent reconstruct instruction opens a review of the saved center. An explicit automatic-search-and-reconstruct request reviews the whole workflow once. Segment All is included only when requested. A known-center reconstruction can also include segmentation; MomoBot asks for the feature when missing and includes segmentation in the confirmation.

The current reconstruction GUI’s confidence-weighted SAM3 scoring and cumulative Gaussian refinement are reused. No new scoring formula is introduced.

## Timing, failure and continuation

A matching measured run or explicit few-slice timing pilot provides a rough runtime range. Timing records include the source size/mtime and relevant reconstruction/preprocessing settings. Otherwise MomoBot says a reliable estimate is unavailable; it does not invent a duration. Automatic search and optional segmentation add time.

Changing the input resets geometry, center, prompt/example and confirmation. The same file being overwritten invalidates the confirmation. A rejected edit cannot partly update a plan or launch it via a stale yes. Cancel pauses planning; Safe Stop requests cancellation of this job. Partial results remain on disk. Retry starts with a new review/offer and a new output folder. Failed trials never become full reconstruction automatically. Restarting the GUI restores the phase and active jobs; it never starts an unfinished confirmation on its own.

Ask what center was used, which slice was searched, how long it took, where the results are, or to open the saved result/curve. Answers use saved jobs matched to the current input. An unset zero is never reported as a computed center. A user-selected trial center is distinguished from an automatically scored center.

After reconstruction, segment these results creates a separate segmentation task using the saved reconstruction folder, preserving the reconstruction history. Training requests create a separate task and ask for the labeled training dataset. Scientific workers remain independent of the chat window.

Requires the current BL62 Reconstruction source/backend (1.2.6 or newer). BL62_RECON_ROOT can select its source directory. Models, environments, data and private chats are external to the Windows launcher release.
