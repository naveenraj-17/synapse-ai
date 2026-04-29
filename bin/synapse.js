#!/usr/bin/env node
'use strict';

const { spawnSync, spawn, execFileSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const http = require('http');
const os = require('os');

const PKG_DIR = path.resolve(__dirname, '..');
const BACKEND_DIR = path.join(PKG_DIR, 'backend');
const FRONTEND_BUILD = path.join(PKG_DIR, 'frontend-build');
const REQUIREMENTS = path.join(BACKEND_DIR, 'requirements.txt');

const SYNAPSE_HOME = path.join(os.homedir(), '.synapse');
const VENV_DIR = path.join(SYNAPSE_HOME, 'venv');
const DATA_DIR = process.env.SYNAPSE_DATA_DIR || path.join(SYNAPSE_HOME, 'data');
const HASH_FILE = path.join(SYNAPSE_HOME, 'requirements.hash');

const BACKEND_PORT = parseInt(process.env.SYNAPSE_BACKEND_PORT || '8765');
const FRONTEND_PORT = parseInt(process.env.SYNAPSE_FRONTEND_PORT || '3000');

// ── Python executable detection ───────────────────────────────────────────────

function pythonCmd() {
  if (os.platform() !== 'win32') return 'python3';
  // On Windows, Python is installed as 'python' (not 'python3')
  const r = spawnSync('python', ['--version'], { stdio: 'pipe' });
  if (r.status === 0) return 'python';
  return 'python3'; // fallback (e.g. via pyenv-win)
}

const PYTHON = pythonCmd();

// ── Prerequisite checks ───────────────────────────────────────────────────────

function checkCmd(cmd) {
  const result = spawnSync(cmd, ['--version'], { stdio: 'pipe' });
  return result.status === 0;
}

function checkPrerequisites() {
  if (!checkCmd(PYTHON)) {
    console.error('Error: python3 not found. Install Python 3.11+ from https://www.python.org/');
    process.exit(1);
  }
  // Verify version >= 3.11
  const result = spawnSync(PYTHON, ['-c', 'import sys; print(sys.version_info[:2])'], { stdio: 'pipe' });
  if (result.status === 0) {
    const out = result.stdout.toString().trim();
    const match = out.match(/\((\d+),\s*(\d+)\)/);
    if (match) {
      const [, major, minor] = match.map(Number);
      if (major < 3 || (major === 3 && minor < 11)) {
        console.error(`Error: Python 3.11+ required, found ${major}.${minor}. Install from https://www.python.org/`);
        process.exit(1);
      }
    }
  }
  if (!checkCmd('npx')) {
    console.error('Error: npx not found. Install Node.js from https://nodejs.org/');
    process.exit(1);
  }
  if (!checkCmd('ollama')) {
    console.warn('Warning: ollama not found. Local models won\'t work; cloud API models still work.');
  }
}

// ── Python venv setup ─────────────────────────────────────────────────────────

function getRequirementsHash() {
  if (!fs.existsSync(REQUIREMENTS)) return null;
  return crypto.createHash('md5').update(fs.readFileSync(REQUIREMENTS)).digest('hex');
}

function venvPython() {
  return os.platform() === 'win32'
    ? path.join(VENV_DIR, 'Scripts', 'python.exe')
    : path.join(VENV_DIR, 'bin', 'python');
}

function venvPip() {
  return os.platform() === 'win32'
    ? path.join(VENV_DIR, 'Scripts', 'pip.exe')
    : path.join(VENV_DIR, 'bin', 'pip');
}

function setupVenv() {
  const currentHash = getRequirementsHash();
  const savedHash = fs.existsSync(HASH_FILE) ? fs.readFileSync(HASH_FILE, 'utf8').trim() : null;

  if (fs.existsSync(venvPython()) && currentHash === savedHash) {
    return; // Already up to date
  }

  if (!fs.existsSync(VENV_DIR)) {
    console.log('Creating Python virtual environment...');
    const result = spawnSync(PYTHON, ['-m', 'venv', VENV_DIR], { stdio: 'inherit' });
    if (result.status !== 0) {
      console.error('Failed to create virtual environment.');
      process.exit(1);
    }
  }

  console.log('Installing Python dependencies (first run, this may take a minute)...');
  const result = spawnSync(venvPip(), ['install', '-r', REQUIREMENTS, '--quiet'], { stdio: 'inherit' });
  if (result.status !== 0) {
    console.error('Failed to install Python dependencies.');
    process.exit(1);
  }

  if (currentHash) fs.writeFileSync(HASH_FILE, currentHash);
}

// ── Data directory ────────────────────────────────────────────────────────────

const DEFAULT_JSON = {
  'user_agents.json': '[]',
  'orchestrations.json': '[]',
  'repos.json': '[]',
  'mcp_servers.json': '[]',
  'custom_tools.json': '[]',
};

function ensureDataDir() {
  fs.mkdirSync(DATA_DIR, { recursive: true });
  for (const sub of ['vault', 'datasets', 'orchestration_runs', 'orchestration_logs']) {
    fs.mkdirSync(path.join(DATA_DIR, sub), { recursive: true });
  }
  for (const [file, content] of Object.entries(DEFAULT_JSON)) {
    const target = path.join(DATA_DIR, file);
    if (!fs.existsSync(target)) fs.writeFileSync(target, content);
  }
}

// ── Process management ────────────────────────────────────────────────────────

function startBackend() {
  const env = {
    ...process.env,
    SYNAPSE_DATA_DIR: DATA_DIR,
    PYTHONPATH: BACKEND_DIR + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : ''),
  };
  return spawn(venvPython(), [path.join(BACKEND_DIR, 'main.py')], {
    cwd: BACKEND_DIR,
    env,
    stdio: 'inherit',
  });
}

function startFrontend() {
  if (!fs.existsSync(FRONTEND_BUILD)) {
    console.error('Error: bundled frontend not found at', FRONTEND_BUILD);
    console.error('The package may be corrupted. Try reinstalling: npm install -g synapse-orch-ai');
    process.exit(1);
  }
  const env = {
    ...process.env,
    PORT: String(FRONTEND_PORT),
    HOSTNAME: '0.0.0.0',
    BACKEND_URL: `http://127.0.0.1:${BACKEND_PORT}`,
    NODE_ENV: 'production',
  };
  return spawn('node', [path.join(FRONTEND_BUILD, 'server.js')], {
    cwd: FRONTEND_BUILD,
    env,
    stdio: 'inherit',
  });
}

function waitForPort(port, name) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const max = 45;
    const check = () => {
      const req = http.get({ host: '127.0.0.1', port, path: '/' }, () => {
        console.log(`  ${name} ready.`);
        resolve();
      });
      req.setTimeout(2000);
      req.on('error', () => {
        if (++attempts < max) setTimeout(check, 2000);
        else reject(new Error(`Timeout waiting for ${name} on port ${port}`));
      });
      req.end();
    };
    check();
  });
}

function openBrowser(url) {
  const platform = os.platform();
  const cmd = platform === 'darwin' ? 'open' : platform === 'win32' ? 'cmd' : 'xdg-open';
  const args = platform === 'win32' ? ['/c', 'start', url] : [url];
  setTimeout(() => {
    try { spawn(cmd, args, { detached: true, stdio: 'ignore' }).unref(); } catch {}
  }, 1000);
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  console.log('Starting Synapse...');
  checkPrerequisites();
  fs.mkdirSync(SYNAPSE_HOME, { recursive: true });
  setupVenv();
  ensureDataDir();

  console.log('Starting backend...');
  const backend = startBackend();

  try {
    await waitForPort(BACKEND_PORT, 'Backend');
  } catch (err) {
    console.error(err.message);
    backend.kill();
    process.exit(1);
  }

  console.log('Starting frontend...');
  const frontend = startFrontend();

  try {
    await waitForPort(FRONTEND_PORT, 'Frontend');
  } catch (err) {
    console.error(err.message);
    backend.kill();
    frontend.kill();
    process.exit(1);
  }

  const url = `http://localhost:${FRONTEND_PORT}`;
  openBrowser(url);
  console.log(`\nSynapse is running at ${url}`);
  console.log('Press Ctrl+C to stop.\n');

  function shutdown() {
    console.log('\nStopping Synapse...');
    backend.kill();
    frontend.kill();
    process.exit(0);
  }

  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
  backend.on('exit', (code) => {
    if (code !== null && code !== 0) {
      console.error(`Backend exited with code ${code}`);
      frontend.kill();
      process.exit(code);
    }
  });
}

main().catch((err) => {
  console.error('Fatal error:', err.message);
  process.exit(1);
});
