# SOP validation — 2026-11-04

The original 118 regression checks were extended with conversation edge cases for one-confirmation dispatch, negative tilts, explicit-only center search, source switches and in-place updates, invalid edits, trial numbering and ambiguity, interrupted reads, cancellation, timing-cache invalidation, restart recovery, preprocessing forwarding, manual/automatic selection and follow-on task creation. All 147 final regression/GUI checks passed before deployment. These tests include fake job submission to verify dispatch boundaries; they are not all GPU computations.

Four native Windows functional chains also passed against existing scientific data:

|Chain|Dataset|Verified result|
|---|---|---|
|Manual center sweep → second numbered candidate → confirm full reconstruction|NMC622_Rod1|2 candidates; one finite, nonconstant 256×256 TIFF; no full job before confirmation|
|Complete Lamino command → one confirmation|Bulk_Pristine|Signed -20° forwarded; one finite, nonconstant 256×256 TIFF; distinct input/output|
|Only automatic center search → wait → explicit full reconstruction|NMC622_Rod1|9 measured centers in 2 rounds, confidence_reward, final step 0.25; saved summary/CSV/curve/overlay; no full job after a bare yes|
|Known center → reconstruction + Segment All|NMC622_Rod1|One reconstructed slice and one segmented image, with saved timing summary and integer labels|

The constrained automatic test searched 1022.5–1024.5 pixels and returned 1023.25. It validates dispatch, persistence and continuation; it is not a new global or physically exact center estimate. The overlay was inspected and detects particles in the sample. The confidence-weighted score was 99.09375, with 143 NMS instances and overlap-excess fraction 0.00385. The raw high-score sample and smoothed peak differ slightly, as expected from the existing smoothing workflow.

The Lamino -20° run above is a functionality test, not a calibration-quality validation of that dataset. No new fine-tuning job or live Telegram message was sent. Instance painting/reference forwarding is covered by adapter/UI regression checks; this release does not claim a new physical instance-prompt accuracy benchmark.
