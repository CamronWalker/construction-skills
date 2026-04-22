# Construction Skills

Claude Code skills for construction workflows. Each subdirectory (`scheduling/`, `estimating/`, `project-management/`, `site-operations/`, `safety/`) is an independently versioned plugin.

## Release Convention

Features and bug fixes go on branches — never commit directly to `main`. Branch name should reflect the work (e.g. `fix/summary-screenshot-black-bar`, `feat/schedule-toolbox`).

On the branch:

1. **Bump plugin version** — increment the version in `{category}/.claude-plugin/plugin.json` (semver, patch for fixes, minor for new skills).
2. **Bump marketplace version** — update the matching plugin entry in `.claude-plugin/marketplace.json` at repo root. Claude Code reads this file to detect available updates; if it's stale, installed instances won't know a new version exists.
3. **Commit** — include both version bumps plus all skill changes in one commit.
4. **Merge to `main`** — via PR or fast-forward merge once the change is reviewed and tested.

After merging to `main`:

5. **Push to origin** — so that any installed Claude Code instance pulling from the repo sees the marketplace bump.
6. **Build** — run `python build.py` at the repo root to produce `src/{plugin}.zip` for each plugin. Pass a plugin name (e.g. `python build.py scheduling`) to build just one.
7. **Distribute** — upload the updated zip(s) to the enterprise plugin distribution for zip-based installs.

The `src/` folder is gitignored — zips are rebuilt locally after each merge and never committed. Both distribution paths are supported: the marketplace (`marketplace.json`) serves direct-from-repo installs; the zip serves enterprise-managed installs.

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
