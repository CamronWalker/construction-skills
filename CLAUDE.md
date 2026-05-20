# Construction Skills

Claude Code skills for construction workflows. Each subdirectory (`scheduling/`, `estimating/`, `project-management/`, `site-operations/`, `safety/`) is an independently versioned plugin.

## Release Convention

Features and bug fixes go on branches — never commit directly to `main`. Branch name should reflect the work (e.g. `fix/summary-screenshot-black-bar`, `feat/schedule-toolbox`).

On the branch:

1. **Bump plugin version** — increment the version in `{category}/.claude-plugin/plugin.json` (semver, patch for fixes, minor for new skills).
2. **Bump marketplace version to match** — update the matching plugin entry in `.claude-plugin/marketplace.json` at repo root to the **exact same version** as step 1. The two version fields must stay in lockstep: Claude Code reads `marketplace.json` to decide "is there a new version?", then checks `plugin.json` to confirm. If they mismatch, update notifications break (stale marketplace → no notification; ahead-of-plugin marketplace → failed install). Every plugin listed in the marketplace needs its own entry; check `marketplace.json` has all six plugins (westland, scheduling, estimating, project-management, site-operations, safety) when adding a new plugin.
3. **Commit** — include both version bumps plus all skill changes in one commit.
4. **Merge to `main`** — via PR or fast-forward merge once the change is reviewed and tested.

After merging to `main`:

5. **Push to origin** — so that any installed Claude Code instance pulling from the repo sees the marketplace bump.
6. **Build** — run `python build.py` at the repo root to produce `src/{plugin}.zip` for each plugin. Pass a plugin name (e.g. `python build.py scheduling`) to build just one.
7. **Distribute** — upload the updated zip(s) to the enterprise plugin distribution for zip-based installs.

The `src/` folder is gitignored — zips are rebuilt locally after each merge and never committed. Both distribution paths are supported: the marketplace (`marketplace.json`) serves direct-from-repo installs; the zip serves enterprise-managed installs.

### Pre-commit version-bump hook

`.githooks/pre-commit` enforces the steps 1–2 rule mechanically: any commit that touches files under a plugin directory must also bump both that plugin's `plugin.json` and the matching `marketplace.json` entry. Commits with a `-dev` suffix in the plugin's `plugin.json` version are exempt (so you can work in-branch without a real bump). Bypass with `--no-verify` only if you know what you're doing.

Activate once per clone (and once in the main repo for any worktrees to inherit it):

```
git config core.hooksPath .githooks
```

Smoke-test the hook locally with `bash .githooks/test_pre_commit.sh`.

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
