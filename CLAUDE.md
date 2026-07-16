# Construction Skills

Claude Code skills for construction workflows. Each subdirectory (`scheduling/`, `estimating/`, `construction/`, `safety/`) is an independently versioned plugin.

## Release Convention

Features and bug fixes go on branches — never commit directly to `main`. Branch name should reflect the work (e.g. `fix/summary-screenshot-black-bar`, `feat/schedule-toolbox`).

On the branch:

1. **Bump plugin version** — increment the version in `{category}/.claude-plugin/plugin.json` (semver, patch for fixes, minor for new skills).
2. **Bump marketplace version to match** — update the matching plugin entry in `.claude-plugin/marketplace.json` at repo root to the **exact same version** as step 1. The two version fields must stay in lockstep: Claude Code reads `marketplace.json` to decide "is there a new version?", then checks `plugin.json` to confirm. If they mismatch, update notifications break (stale marketplace → no notification; ahead-of-plugin marketplace → failed install). Every plugin listed in the marketplace needs its own entry; check `marketplace.json` has all five plugins (westland, scheduling, estimating, construction, safety) when adding a new plugin.
3. **Commit** — include both version bumps plus all skill changes in one commit.
4. **Merge to `main`** — via PR or fast-forward merge once the change is reviewed and tested.

After merging to `main`:

5. **Push to origin** — so that any installed Claude Code instance pulling from the repo sees the marketplace bump.
6. **Build in the main repo working tree, not a worktree.** From `C:\Users\camron\code\construction-skills\` (the main checkout — not under `.claude/worktrees/...`):
   ```
   git switch main          # release the feature branch if you were on it
   git pull --ff-only       # pick up the merged PR
   python build.py scheduling   # or omit the plugin name to build all
   ```
   The build writes `src/{plugin}.zip` *relative to the current working directory*, so building from a worktree puts the zip inside the worktree's `src/` — invisible to the distribution path you upload from. Always cd to the main checkout first. If a worktree currently has `main` checked out (which blocks `git switch main` in the main repo), `git switch <feature-branch>` inside the worktree to release it, then switch the main repo.
7. **Distribute** — upload the updated zip(s) from the main repo's `src/` to the enterprise plugin distribution for zip-based installs.

The `src/` folder is gitignored — zips are rebuilt locally after each merge and never committed. Both distribution paths are supported: the marketplace (`marketplace.json`) serves direct-from-repo installs; the zip serves enterprise-managed installs.

### CI enforcement (PR checks)

[`.github/workflows/lint.yml`](.github/workflows/lint.yml) runs on every pull request to `main` and gates merge with two jobs:

- **version-bump** — for each plugin with any file changed in the PR, requires (1) a `+"version":` line in both that plugin's `plugin.json` and the corresponding `marketplace.json` entry; (2) the head version is *strictly greater* than the base version in both files — downgrades and no-op re-statements fail the check; (3) `plugin.json` version equals the `marketplace.json` entry version at head (lockstep). `-dev`-suffixed versions are exempt so in-branch iteration doesn't trip the gate. Mirrors the rule the local pre-commit hook used to enforce, but operates on the full PR diff (base..head) and runs on every contributor without setup.
- **forbid-personal-paths** — fails the PR if any *newly added* line contains a `C:\Users\<name>\` path (any user, any separator, case-insensitive). Catches per-user hardcodes from any contributor — code should use env vars, `~` expansion, or repo-relative paths. Documentation files (`*.md`, `docs/**`) and this workflow itself are excluded — illustrative mentions in prose are fine; only code-side hardcodes are caught.

## Structure

```
{category}/
  .claude-plugin/
    plugin.json        # version lives here
  skills/
    {skill-name}/
      SKILL.md
```

## Adding a New Skill

1. Create `skills/{skill-name}/SKILL.md` under the appropriate category
2. Register it in `{category}/.claude-plugin/plugin.json`
3. Follow the release convention above

## Continuous Improvement Loop

Skills improve by running against real work and feeding the gaps back. The standing loop for every skill in this repo:

1. **Use the skill on a real project.** Save the Claude-generated output (XER, PDF, email draft, whatever the skill produces) in the project folder.
2. **Compare against what actually shipped.** When the human-submitted version differs meaningfully from Claude's output — WBS structure wrong, logic approach different, artifacts missing, tone off — that's a signal worth capturing.
3. **Write a `Lessons Learned - <Project>.md` next to the Claude output.** Record each divergence as its own numbered section with: *what the scheduler/PM/etc. did*, *what Claude did*, *why it matters*, *proposed skill gap and fix*. Order by severity.
4. **Run a skill-improvement session.** Point Claude at the lessons-learned doc plus the skill folder. Output is a branch that updates the skill per the release convention above.
5. **Release.** Version bump → commit → merge → `python build.py` → distribute.

The SFJHS proposal schedule (`~Proposal Schedules/Spanish Fork Jr High/Proposal Schedule/Lessons Learned - SFJHS Proposal Schedule.md`) is the template for what step 3 looks like in practice.

**Why this works:** Skills describe *how* to do work; they can't anticipate every judgement call a real project forces. A skill that's been through 5 lessons-learned cycles against 5 different projects is five steps closer to general — and the improvement is bounded and reviewable each time, not a theoretical refactor.
