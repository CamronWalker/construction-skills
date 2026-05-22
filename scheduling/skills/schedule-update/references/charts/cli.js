#!/usr/bin/env node
// cli.js — read {slug}.json payloads from a dir, dispatch via RENDERERS,
// write {slug}.html + {slug}.png to an output dir.

import { readdirSync, readFileSync, writeFileSync, mkdirSync, existsSync, statSync } from 'node:fs';
import { resolve, join, dirname } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { RENDERERS } from './registry.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const HTML_TO_PNG = resolve(__dirname, 'html_to_png.cjs');
const CARD_W = 1728;
const CARD_H = 432;
const SCALE  = 2;

function main() {
  const [payloadDir, outputDir] = process.argv.slice(2);
  if (!payloadDir || !outputDir) {
    console.error('Usage: node cli.js <payload_dir> <output_dir>');
    process.exit(2);
  }
  if (!existsSync(payloadDir) || !statSync(payloadDir).isDirectory()) {
    console.error(`payload dir not found or not a directory: ${payloadDir}`);
    process.exit(2);
  }
  mkdirSync(outputDir, { recursive: true });

  /** @type {Array<{slug: string, path: string}>} */
  const rendered = [];
  /** @type {Array<{slug: string, reason: string}>} */
  const failed = [];

  const files = readdirSync(payloadDir).filter(f => f.endsWith('.json')).sort();
  for (const file of files) {
    const slug = file.replace(/\.json$/, '');
    const fn = RENDERERS[slug];
    if (!fn) {
      failed.push({ slug, reason: 'no renderer in registry' });
      continue;
    }
    try {
      const payload = JSON.parse(readFileSync(join(payloadDir, file), 'utf-8'));
      const { html } = fn(payload);
      const htmlPath = join(outputDir, `${slug}.html`);
      const pngPath  = join(outputDir, `${slug}.png`);
      writeFileSync(htmlPath, html, 'utf-8');
      const result = spawnSync('node',
        [HTML_TO_PNG, htmlPath, pngPath, String(CARD_W), String(CARD_H), String(SCALE)],
        { encoding: 'utf-8', timeout: 60_000 });
      if (result.signal) {
        throw new Error(`html_to_png.cjs killed by ${result.signal} (likely timeout after 60s)`);
      }
      if (result.status !== 0) {
        const stderr = (result.stderr || '').trim();
        throw new Error(`html_to_png.cjs exited ${result.status}: ${stderr.slice(0, 500)}`);
      }
      rendered.push({ slug, path: pngPath });
    } catch (err) {
      const e = err instanceof Error ? err : new Error(String(err));
      failed.push({ slug, reason: `${e.name}: ${e.message}` });
    }
  }

  console.log(JSON.stringify({ rendered, failed }, null, 2));
  process.exit(failed.length ? 1 : 0);
}

main();
