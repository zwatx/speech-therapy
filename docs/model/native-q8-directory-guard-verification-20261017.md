# Directory guard correction: generated filesystem verification

The corrected export helper passed six generated filesystem checks. This verifies
the directory predicate only; no model session, inference, prediction, recording
or simulator operation was performed.

The change removes the requirement that a mutable parent directory retain its
link count while an output file is created. Canonical path, private permissions,
owner/group and device/inode checks remain. Immutable file checks are unchanged.
The original failed exporter is preserved separately.

The actual test accepted the original private directory before and after creating
one synthetic byte, observed its link count change from two to three, rejected
changed permissions, accepted restored permissions, rejected a replacement inode
and rejected a symlink alias. Its fixture directory was left empty. These checks
call the actual corrected predicate; the included exporter entry is never called.

The directly invoked controller exited successfully in 4.608 seconds. Compile,
link and test stages each exited normally, with no cleanup errors or remaining
owned processes. Root verified all 103 frozen source/tool bindings and all 209
reported compiler inputs. Complete implicit SDK/linker input provenance remains
unestablished; this is a narrowly scoped control, not shipping or performance
qualification.

The [independent result review](../../work/native-q8-directory-guard-correction-20261017/RESULT-REVIEW.md)
is clear for this limited checkpoint. Sources, process receipts and retained
products are under `work/native-q8-directory-guard-correction-20261017/`.

The prior graph export remains failed and its output unadmitted. The previous
22/24 preservation result and q8 exclusion from learner feedback are unchanged.
A fresh graph comparison needs its own reviewed preparation; this control does
not validate an export or identify the unique predicate that failed historically.
