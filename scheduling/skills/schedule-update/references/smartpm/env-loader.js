/**
 * Reads SmartPM credentials from `~/.claude/.env`.
 *
 * Required keys:  SMARTPM_EMAIL, SMARTPM_PASSWORD
 * Optional keys:  SMARTPM_PROJECTS_URL (defaults to Westland's v2 cards URL)
 *                 SMARTPM_BASE_URL     (defaults to https://live.smartpmtech.com)
 *
 * Module API:
 *   loadConfig({ interactive }) -> { email, password, projectsUrl, baseUrl }
 *   readEnvFile()               -> { KEY: 'value', ... }
 *   upsertEnvFile({ KEY: 'value', ... })
 *   ENV_PATH                    -> absolute path to ~/.claude/.env
 *
 * CLI:  node env-loader.js setup  -> interactive setup wizard
 *       node env-loader.js show   -> prints which keys are present (values redacted)
 */

const fs = require('fs');
const path = require('path');
const os = require('os');
const readline = require('readline');

const ENV_PATH = path.join(os.homedir(), '.claude', '.env');

const DEFAULT_PROJECTS_URL =
  'https://live.smartpmtech.com/#/v2/39032af1-4b5c-4d22-a81e-9f7c7aabfbc5/projects/cards';
const DEFAULT_BASE_URL = 'https://live.smartpmtech.com';

function parseEnv(content) {
  const env = {};
  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq < 0) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    env[key] = value;
  }
  return env;
}

function readEnvFile() {
  if (!fs.existsSync(ENV_PATH)) return {};
  return parseEnv(fs.readFileSync(ENV_PATH, 'utf8'));
}

/**
 * Upsert env vars into ~/.claude/.env, preserving existing keys, comments,
 * and ordering. Replaces in place when a key already exists; appends otherwise.
 */
function upsertEnvFile(updates) {
  fs.mkdirSync(path.dirname(ENV_PATH), { recursive: true });
  const content = fs.existsSync(ENV_PATH)
    ? fs.readFileSync(ENV_PATH, 'utf8')
    : '';
  const lines = content.split(/\r?\n/);
  const seen = new Set();
  const out = [];
  for (const line of lines) {
    const m = line.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=/);
    if (m && Object.prototype.hasOwnProperty.call(updates, m[1])) {
      seen.add(m[1]);
      out.push(`${m[1]}=${updates[m[1]]}`);
    } else {
      out.push(line);
    }
  }
  while (out.length && !out[out.length - 1].trim()) out.pop();
  for (const [key, value] of Object.entries(updates)) {
    if (!seen.has(key)) out.push(`${key}=${value}`);
  }
  out.push('');
  fs.writeFileSync(ENV_PATH, out.join('\n'), 'utf8');
}

function promptVisible(question) {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      rl.close();
      resolve(answer);
    });
  });
}

function promptHidden(question) {
  // No-echo input. Falls back to visible read on terminals without TTY support.
  if (!process.stdin.isTTY) return promptVisible(question);
  const ETX = String.fromCharCode(3);   // Ctrl+C
  const BS = String.fromCharCode(8);    // Backspace
  const DEL = String.fromCharCode(127); // Delete key on most terminals
  return new Promise((resolve) => {
    process.stdout.write(question);
    let input = '';
    process.stdin.setRawMode(true);
    process.stdin.resume();
    process.stdin.setEncoding('utf8');
    const onData = (data) => {
      const ch = data.toString('utf8');
      if (ch === '\r' || ch === '\n' || ch === '\r\n') {
        process.stdin.setRawMode(false);
        process.stdin.pause();
        process.stdin.removeListener('data', onData);
        process.stdout.write('\n');
        resolve(input);
      } else if (ch === ETX) {
        process.exit(130);
      } else if (ch === DEL || ch === BS) {
        if (input.length > 0) input = input.slice(0, -1);
      } else {
        input += ch;
      }
    };
    process.stdin.on('data', onData);
  });
}

async function runSetupWizard(missingKeys) {
  process.stderr.write('\n=== SmartPM credentials setup ===\n');
  process.stderr.write(`Saving to: ${ENV_PATH}\n\n`);
  const updates = {};
  if (missingKeys.includes('SMARTPM_EMAIL')) {
    const v = (await promptVisible('SmartPM email: ')).trim();
    if (!v) throw new Error('SMARTPM_EMAIL is required');
    updates.SMARTPM_EMAIL = v;
  }
  if (missingKeys.includes('SMARTPM_PASSWORD')) {
    const v = (await promptHidden('SmartPM password: ')).trim();
    if (!v) throw new Error('SMARTPM_PASSWORD is required');
    updates.SMARTPM_PASSWORD = v;
  }
  upsertEnvFile(updates);
  process.stderr.write(`\nSaved to ${ENV_PATH}\n\n`);
  return updates;
}

async function loadConfig({ interactive = false } = {}) {
  const env = readEnvFile();
  const config = {
    email: env.SMARTPM_EMAIL || '',
    password: env.SMARTPM_PASSWORD || '',
    projectsUrl: env.SMARTPM_PROJECTS_URL || DEFAULT_PROJECTS_URL,
    baseUrl: env.SMARTPM_BASE_URL || DEFAULT_BASE_URL,
  };
  const missing = [];
  if (!config.email) missing.push('SMARTPM_EMAIL');
  if (!config.password) missing.push('SMARTPM_PASSWORD');
  if (missing.length === 0) return config;
  if (!interactive) {
    const err = new Error(
      `Missing in ${ENV_PATH}: ${missing.join(', ')}\n` +
        `Run: node "${path.join(__dirname, 'env-loader.js')}" setup`
    );
    err.code = 'ENV_MISSING';
    err.missingKeys = missing;
    throw err;
  }
  const updates = await runSetupWizard(missing);
  return {
    ...config,
    email: updates.SMARTPM_EMAIL || config.email,
    password: updates.SMARTPM_PASSWORD || config.password,
  };
}

module.exports = {
  ENV_PATH,
  DEFAULT_PROJECTS_URL,
  DEFAULT_BASE_URL,
  loadConfig,
  readEnvFile,
  upsertEnvFile,
  runSetupWizard,
};

if (require.main === module) {
  const cmd = process.argv[2] || 'show';
  (async () => {
    if (cmd === 'setup') {
      const env = readEnvFile();
      const missing = [];
      if (!env.SMARTPM_EMAIL) missing.push('SMARTPM_EMAIL');
      if (!env.SMARTPM_PASSWORD) missing.push('SMARTPM_PASSWORD');
      if (missing.length === 0) {
        process.stderr.write(
          `SMARTPM_EMAIL and SMARTPM_PASSWORD are already set in ${ENV_PATH}.\n` +
            'Re-run with `setup --force` to overwrite.\n'
        );
        if (process.argv[3] !== '--force') process.exit(0);
        await runSetupWizard(['SMARTPM_EMAIL', 'SMARTPM_PASSWORD']);
      } else {
        await runSetupWizard(missing);
      }
    } else if (cmd === 'show') {
      const env = readEnvFile();
      const keys = ['SMARTPM_EMAIL', 'SMARTPM_PASSWORD', 'SMARTPM_PROJECTS_URL', 'SMARTPM_BASE_URL'];
      for (const k of keys) {
        const v = env[k];
        if (!v) {
          process.stdout.write(`${k}=<missing>\n`);
        } else if (k === 'SMARTPM_PASSWORD') {
          process.stdout.write(`${k}=<set, ${v.length} chars>\n`);
        } else {
          process.stdout.write(`${k}=${v}\n`);
        }
      }
    } else {
      process.stderr.write(`Unknown command: ${cmd}\nUsage: node env-loader.js [setup|show]\n`);
      process.exit(2);
    }
  })().catch((err) => {
    process.stderr.write(`ERROR: ${err.message}\n`);
    process.exit(1);
  });
}
