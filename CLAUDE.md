# Construction Skills

Claude Code skills for construction workflows. Each subdirectory (`scheduling/`, `estimating/`, `project-management/`, `site-operations/`, `safety/`) is an independently versioned plugin.

## Release Convention

Every change that modifies skills must follow this sequence before committing:

1. **Bump version** — increment the version in `{category}/.claude-plugin/plugin.json` (semver, patch for fixes, minor for new skills)
2. **Zip to src** — zip the entire `{category}/` directory into `src/{category}.zip`
   ```bash
   cd /path/to/construction-skills
   mkdir -p src
   zip -r src/{category}.zip {category}/
   ```
3. **Commit and push** — include the bumped plugin.json, all skill changes, and the updated zip in one commit

`src/` is gitignored for local builds but the zips **are** committed — they are the distributable artifacts.

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
