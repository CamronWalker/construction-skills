// tests/workers-import.test.js — confirms the package bundles cleanly for
// Cloudflare Workers (no node:fs / node:path / etc. sneaking into renderer
// code via a future commit).

import { describe, it, expect } from 'vitest';
import { execSync, spawnSync } from 'node:child_process';
import { writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve, join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const CHARTS_DIR = resolve(__dirname, '..');

function wranglerInstalled() {
  try { execSync('npx --no-install wrangler --version', { stdio: 'ignore' }); return true; }
  catch { return false; }
}

describe('Cloudflare Workers compatibility', () => {
  it.skipIf(!wranglerInstalled())('wrangler can bundle the package without Node-only imports', () => {
    const shim = join(tmpdir(), `westland-charts-smoke-${Date.now()}`);
    mkdirSync(shim, { recursive: true });
    try {
      const chartsAbs = CHARTS_DIR.replace(/\\/g, '/');
      writeFileSync(join(shim, 'wrangler.toml'),
        `name = "smoke"\nmain = "worker.js"\ncompatibility_date = "2024-11-01"\n`);
      writeFileSync(join(shim, 'worker.js'),
        `import { RENDERERS, CHART_META, renderPlaceholder } from '${chartsAbs}/index.js';\n` +
        `export default { async fetch() {\n` +
        `  return new Response(JSON.stringify({ renderers: Object.keys(RENDERERS), metas: Object.keys(CHART_META) }), { headers: { 'content-type': 'application/json' } });\n` +
        `}};\n`);
      const result = spawnSync('npx',
        ['wrangler', 'deploy', '--dry-run', '--outdir', join(shim, 'out')],
        { cwd: shim, encoding: 'utf-8', timeout: 90_000 });
      if (result.status !== 0) {
        throw new Error(`wrangler bundle failed (${result.status}):\n${result.stdout}\n${result.stderr}`);
      }
      const combined = (result.stdout + result.stderr).toLowerCase();
      expect(combined).not.toMatch(/used by your worker.*?node:(fs|path|child_process|os|crypto)/);
    } finally {
      try { rmSync(shim, { recursive: true, force: true }); } catch {}
    }
  });
});
