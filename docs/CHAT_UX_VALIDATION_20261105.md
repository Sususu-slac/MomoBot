# Chat navigation validation — MomoBot 0.9.1

190 native Windows unit/GUI checks passed, including 14 new navigation checks. Existing chat/SOP fixtures now explicitly create a task when they need one; production startup never creates or opens a task automatically.

New coverage: first launch; saved history without auto-selection; exactly one task created by the first message; reuse on subsequent messages; fresh page on restart; preservation of saved drafts/history; blank input and refreshing while typing; explicit New task; attachment selection/cancellation from the fresh page; model-first reconstruction on first send; delayed reply growth and line wrapping; viewport resizing; reading history without jumping; resuming follow on send; and restoring scroll position on task switches.

A separate native GUI check used the current user's existing Gemma server, with isolated conversations/jobs. Sending the first reconstruction request from a fresh page created a task and called Gemma (3.58 seconds observed). Reopening displayed a fresh page while preserving both saved tasks and the previous draft. Synthetic long messages and resizing ended exactly at the latest scroll position (0 px gap). No scientific jobs were submitted. The model was not downloaded, replaced or stopped by this check.

The Windows launcher self-test asserts fresh_chat=True, direct_chat_enabled=True and model_first_reconstruction=True. Private state, screenshots and local test evidence are excluded from release packages.
