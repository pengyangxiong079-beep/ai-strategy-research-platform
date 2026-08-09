# Revision model

`rev_000` is the immutable Initial Snapshot. It is visible for comparison but excluded from the user revision count. `rev_001` and later revisions record parent revision, status, type, rerun/preserved stages, invalidated artifacts, input/output hashes, timestamps, and errors.

A Fact-only revision starts at Fact Verification and reruns downstream stages. A full re-research revision starts at Data Acquisition and invalidates dependent artifacts. Copying files and changing only a revision ID is not considered a successful revision.
