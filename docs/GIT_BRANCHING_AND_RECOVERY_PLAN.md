# Git Branching and Recovery Plan

## Objective

Protect the current working implementation while safely recovering files from the historical "Approach B" (code-split/repository-organization) commits that may be retrieved from a college PC.

---

## Current Repository State

| Property | Value |
|----------|-------|
| **Current branch** | `main` |
| **HEAD** | `7547309` — "Finalize reproducible project repository and transfer setup" |
| **Previous commit** | `bb27b01` — "Initial commit: Reorganized SIH 3D pipeline with modular architecture and patches" |
| **Remote** | `origin/main` — up to date |
| **Tags** | None |
| **Uncommitted changes** | None (clean working tree) |
| **Total commits** | 2 |

### Current Commit History
```
7547309 Finalize reproducible project repository and transfer setup
bb27b01 Initial commit: Reorganized SIH 3D pipeline with modular architecture and patches
```

---

## Known Empty Files (Approach B Artifacts)

The repository reorganization (Approach B) left several **empty (0-byte) files** that previously had content:

| File | Size | Expected Content |
|------|------|-----------------|
| `src/pipeline/ingest_telemetry.py` | 0 bytes | Frame extraction + SRT parsing |
| `scripts/testing/run_colmap.py` | 0 bytes | COLMAP test script |
| `scripts/testing/run_quality_gate.py` | 0 bytes | Progressive quality gate script |

These files contain function stubs/names in the commit but no actual code. The original working code existed in a different directory layout before the reorganization.

---

## Approach B Definition

**Approach B** refers to the repository-organization/code-split work done on a separate machine (college PC). Key characteristics:
- Reorganized files from flat structure into `src/pipeline/`, `scripts/`, etc.
- Created patches for third-party repos
- Set up `.gitignore` and `.gitattributes`
- **May have introduced empty files** during the move (files referenced but not copied)
- The college PC may have additional commits with the actual file contents

---

## Safety Strategy

### Rule 1: Current `main` is PROTECTED

The current HEAD (`7547309`) is the known-good state. It must not be modified by any Approach B recovery operation.

### Rule 2: Tag Before Any Recovery

Before any Approach B files are introduced:
```bash
git tag pre-recovery-safe main
```

This creates an immutable reference point that can always be returned to.

### Rule 3: Recovery Branch is ISOLATED

All Approach B content arrives on a separate branch:
```bash
git checkout -b approach-b-recovery main
```

The `main` branch is never directly modified by recovery operations.

### Rule 4: Cherry-pick ONLY Validated Files

Individual files are cherry-picked or manually copied — never a full merge.

---

## Recovery Procedure

### Step 1: Before Retrieving Anything

```bash
# Tag current safe state
git tag pre-recovery-safe main

# Verify tag
git log --oneline pre-recovery-safe
# Should show: 7547309 Finalize reproducible project repository...
```

### Step 2: Retrieve Approach B Commits

The user brings commits from the college PC. Two possible scenarios:

**Scenario A: USB drive with `.git` bundle**
```bash
# Import bundle
git bundle verify approach-b.bundle
git fetch approach-b.bundle approach-b-branch:approach-b-recovery
```

**Scenario B: Same remote, different branch**
```bash
git fetch origin
git checkout -b approach-b-recovery origin/approach-b-branch
```

**Scenario C: Direct file copy (no git)**
```bash
# Create recovery branch
git checkout -b approach-b-recovery main

# Copy files manually from USB/folder into working directory
# Stage and commit
git add -A
git commit -m "Import Approach B files for inspection"
```

### Step 3: Inspect Without Applying

```bash
# View what changed
git diff main..approach-b-recovery --stat

# View specific file content
git show approach-b-recovery:src/pipeline/ingest_telemetry.py

# Check if a file has actual content (not empty)
git show approach-b-recovery:src/pipeline/ingest_telemetry.py | wc -l
```

### Step 4: Compare Old and Current Versions

```bash
# Side-by-side diff for specific file
git diff main..approach-b-recovery -- src/pipeline/ingest_telemetry.py

# List ALL files that differ
git diff main..approach-b-recovery --name-status
```

### Step 5: Selectively Recover Useful Files

For each file that has content in Approach B but is empty/missing in current `main`:

```bash
# Switch to main
git checkout main

# Create implementation branch (NOT approach-b-recovery)
git checkout -b demo-implementation main

# Copy ONLY the specific file from approach-b-recovery
git checkout approach-b-recovery -- src/pipeline/ingest_telemetry.py

# Review the content
cat src/pipeline/ingest_telemetry.py

# If good, stage and commit
git add src/pipeline/ingest_telemetry.py
git commit -m "Recover ingest_telemetry.py from Approach B"
```

### Step 6: Verify After Recovery

```bash
# Ensure the build still works
python scripts/testing/verify_pipeline_imports.py

# Ensure no other files were accidentally modified
git diff main..demo-implementation --stat
```

---

## Conflict Prevention

### What Could Conflict

| Risk | Likelihood | Prevention |
|------|-----------|------------|
| Empty files overwritten with content | **Expected** — this is the goal | Review content before accepting |
| Working files overwritten with old versions | **Medium** | Never merge entire branch; cherry-pick only |
| `.gitignore` / config changes | **Low** | Inspect diff before accepting |
| Third-party patches overwritten | **Low** | Patches are in `patches/` and should be identical |
| `requirements.txt` changed | **Medium** | Keep current version; manually merge if needed |

### Prevention Rules

1. **Never run `git merge approach-b-recovery` on main**
2. **Never run `git rebase` involving Approach B commits on main**
3. **Always use `git checkout <branch> -- <file>` for individual file recovery**
4. **Always review `git diff` before staging recovered files**
5. **Always verify imports after recovery**

---

## Branch Strategy for Implementation

```
main (protected)
 │
 ├── pre-recovery-safe (tag)
 │
 ├── approach-b-recovery (inspection only, never merged)
 │
 └── demo-implementation (working branch for new demo)
      │
      ├── Recovered files from approach-b-recovery
      ├── New frontend code
      ├── New backend code
      └── All new demo implementation
```

### Branch Lifecycle

1. **main**: Protected. Only receives merges from `demo-implementation` after full testing.
2. **approach-b-recovery**: Read-only reference. Deleted after all useful files are recovered.
3. **demo-implementation**: Active development branch. Both frontend and backend developers work here (or create feature branches off it).

---

## Cherry-pick Policy

### When Cherry-pick IS Appropriate
- Recovering a single file that is empty in current repo but has content in Approach B
- Recovering a specific bug fix that was applied in Approach B
- Recovering documentation that was added in Approach B

### When Cherry-pick is NOT Appropriate
- The Approach B commit reorganizes many files simultaneously
- The commit contains mixed changes (some good, some bad)
- The commit references files/paths that no longer exist
- The commit modifies third-party code in ways we've already patched differently

### Preferred Alternative to Cherry-pick
For most cases, **manual file copy** (`git checkout <branch> -- <file>`) is safer than cherry-pick because:
- Cherry-pick applies an entire commit (may include unwanted changes)
- File checkout copies exactly one file
- No merge conflict resolution needed

---

## File Reconciliation Strategy

For each file in Approach B that differs from current `main`:

| Situation | Action |
|-----------|--------|
| File is empty in main, has content in Approach B | **RECOVER** via `git checkout` |
| File exists and is identical | **SKIP** — nothing to do |
| File exists but differs in both | **COMPARE** — review diff, keep the better version |
| File exists in Approach B but not in main | **EVALUATE** — is it needed for the demo? |
| File exists in main but not in Approach B | **KEEP** — Approach B may have deleted it incorrectly |

### Priority Recovery Files

Based on current repository inspection, these are the files most likely to need recovery:

1. **`ingest_telemetry.py`** — CRITICAL: frame extraction is required for the pipeline
2. **`run_quality_gate.py`** — LOW: historical testing script, not needed for demo
3. **`run_colmap.py`** — LOW: COLMAP path is not the demo path

---

## Emergency Rollback

If anything goes wrong during recovery:

```bash
# Return to known-good state
git checkout main
git reset --hard pre-recovery-safe

# Verify
git log --oneline -1
# Should show: 7547309
```

If the `demo-implementation` branch is corrupted:

```bash
# Delete and recreate
git branch -D demo-implementation
git checkout -b demo-implementation pre-recovery-safe
```

---

## Important: New Implementation vs Recovery

The demo implementation (new frontend, new backend FastAPI layer, enhanced Poisson filtering) should be **written fresh**, not recovered from Approach B.

Approach B recovery is ONLY for:
- The `ingest_telemetry.py` frame extraction code (if it exists and is correct)
- Any other specific module that was lost during reorganization

Everything else (FastAPI app, React frontend, measurement service, etc.) is NEW CODE that never existed in Approach B.
