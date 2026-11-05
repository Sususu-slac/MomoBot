# Linked viewers validation — MomoBot 0.10.1

214 native Windows unit/GUI checks passed, including 24 viewer checks. GitHub Windows checks run the complete suite against the released source.

Coverage includes trusted assistant-only link dispatch; persistent links and lazy migration of older conversations; nonmodal window reuse; projection/flat/dark routing; read-only uint16/float32 display; picking a search row; transactional parameter edits; invalid range rollback; input-file replacement and deleted-task guards; choosing the exact numbered center or signed angle; original-task binding after chat switches; obsolete-trial protection; natural result ordering; files arriving during reconstruction (including out-of-order slices); late preview responses; bounded caching; locked comparison display; and retaining zoom across candidates.

A separate isolated native GUI check used the existing nmc_last_1_132 HDF5 (601 projections, 1212 × 1616, uint16, about 2.48 GB), its 100 actual saved trial candidates, and an existing independent 2048-slice reconstruction stack. The first input preview took 0.25–0.27 seconds, trial preview 0.31–0.33 seconds and full-result browser 0.52–0.67 seconds in these local runs. A 20 ms GUI heartbeat had a maximum observed gap of about 0.25 seconds while opening/loading the windows. These are small local functional samples, not guaranteed performance.

Selecting the middle trial candidate transferred exactly the displayed 808.5 px value and stopped at the confirmation review. This was an arbitrary functional selection, not a recommendation or reconstruction-quality assessment. Source HDF5 size/mtime were unchanged. The scientific-submit method was blocked: no new reconstruction, SAM3 or training job ran. Screenshots, paths and test conversations stay local and are excluded from public packages.

Preview reads occur in background workers; each viewer retains at most four display images, downsampled to a longest side of 1536 pixels. Display conversion and window/level edits never overwrite HDF5/TIFF pixels or alter SAM3 input preparation. This version browses standard HDF5 projection/flat/dark frames and saved 2D slice image stacks, not packed 3D TIFF volumes.

Viewer links are task/job-bound desktop actions, not model-generated executable URLs. GUI parameter edits use the same deterministic SOP validation. Invalid edits cannot partly commit; trial selection reviews the reconstruction plan and never starts full reconstruction without confirmation. The existing local model, environments and GPU allocation are unchanged.
