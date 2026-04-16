# Construction Skills

Claude Code skills for construction workflows. Each subdirectory (`scheduling/`, `estimating/`, `project-management/`, `site-operations/`, `safety/`) is an independently versioned plugin.

## Release Convention

Every change that modifies skills must follow this sequence before committing:

1. **Bump version** — increment the version in `{category}/.claude-plugin/plugin.json` (semver, patch for fixes, minor for new skills)
2. **Commit** — include the bumped plugin.json and all skill changes in one commit

The `src/` zip is for internal team distribution only — it is gitignored and never committed.

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
