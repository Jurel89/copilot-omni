---
name: omni-ship
description: Commit changes, push branch, open PR, and monitor CI for the current run.
---

# /omni-ship

Chains `git-master` agent → `verifier` agent → `gh pr create` for the current branch. Use after a run's verification phase passes.
