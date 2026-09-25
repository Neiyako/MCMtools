/**
 * Panel test runner.
 *
 * Starts the real MCMtools server against the demo project, then runs the four
 * panel test files against it. The panel is only meaningful against a live API,
 * so these are integration tests by design -- a panel tested against mocks
 * would pass while showing the user nothing.
 */
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..', '..');
const PORT = process.env.PORT || '8467';
const BASE = `http://127.0.0.1:${PORT}`;
const PROJECT = process.env.PROJECT || 'examples/demo_pcql';

function log(msg) { process.stdout.write(msg + '\n'); }

async function waitForServer(timeoutMs = 20000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(`${BASE}/api/health`);
      if (res.ok) return true;
    } catch { /* not up yet */ }
    await new Promise(r => setTimeout(r, 300));
  }
  return false;
}

function run(file) {
  return new Promise((resolve) => {
    const p = spawn(process.execPath, [path.join(here, file)], {
      env: { ...process.env, BASE },
      stdio: 'inherit',
    });
    p.on('exit', (code) => resolve(code ?? 1));
  });
}

const mcm = path.join(root, 'core', 'mcm');
if (!fs.existsSync(mcm)) {
  log(`cannot find the mcm launcher at ${mcm}`);
  process.exit(1);
}

log(`starting: ${mcm} --dir ${PROJECT} serve --port ${PORT}`);
const server = spawn(mcm, ['--dir', PROJECT, 'serve', '--port', PORT], {
  cwd: root, stdio: ['ignore', 'pipe', 'pipe'],
});
let serverLog = '';
server.stdout.on('data', d => { serverLog += d; });
server.stderr.on('data', d => { serverLog += d; });

const cleanup = () => { try { server.kill('SIGTERM'); } catch { /* gone */ } };
process.on('exit', cleanup);
process.on('SIGINT', () => { cleanup(); process.exit(130); });

let code = 0;
try {
  if (!await waitForServer()) {
    log('server did not come up. Output:\n' + serverLog);
    cleanup();
    process.exit(1);
  }
  log(`server ready at ${BASE}\n`);

  for (const file of ['logic.test.mjs', 'badges.test.mjs', 'render.test.mjs', 'flows.test.mjs', 'figsearch.test.mjs', 'diy.test.mjs']) {
    log(`\n${'='.repeat(60)}\n${file}\n${'='.repeat(60)}`);
    const rc = await run(file);
    if (rc !== 0) code = rc;
  }
} finally {
  cleanup();
}

log(code === 0 ? '\nPANEL: all checks passed' : `\nPANEL: failures (exit ${code})`);
process.exit(code);
