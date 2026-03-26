#!/usr/bin/env node
/**
 * Bundle the Next.js standalone build into frontend-build/
 * Run this before publishing the npm package.
 */
'use strict';

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const FRONTEND_DIR = path.join(ROOT, 'frontend');
const DEST_DIR = path.join(ROOT, 'frontend-build');

function exec(cmd, cwd) {
  execSync(cmd, { cwd: cwd || ROOT, stdio: 'inherit' });
}

function copyDir(src, dest) {
  execSync(`cp -r "${src}/." "${dest}/"`, { stdio: 'inherit' });
}

console.log('Installing frontend dependencies...');
exec('npm ci', FRONTEND_DIR);

console.log('Building Next.js standalone...');
exec('npm run build', FRONTEND_DIR);

const standaloneSrc = path.join(FRONTEND_DIR, '.next', 'standalone');
if (!fs.existsSync(standaloneSrc)) {
  console.error('Error: .next/standalone not found after build.');
  console.error('Make sure next.config.ts has output: "standalone"');
  process.exit(1);
}

console.log('Copying standalone build to frontend-build/...');
if (fs.existsSync(DEST_DIR)) fs.rmSync(DEST_DIR, { recursive: true });
fs.mkdirSync(DEST_DIR, { recursive: true });

copyDir(standaloneSrc, DEST_DIR);

const staticSrc = path.join(FRONTEND_DIR, '.next', 'static');
const staticDest = path.join(DEST_DIR, '.next', 'static');
fs.mkdirSync(path.join(DEST_DIR, '.next'), { recursive: true });
exec(`cp -r "${staticSrc}" "${staticDest}"`);

const publicSrc = path.join(FRONTEND_DIR, 'public');
if (fs.existsSync(publicSrc)) {
  exec(`cp -r "${publicSrc}" "${path.join(DEST_DIR, 'public')}"`);
}

console.log('Done. Frontend bundled into frontend-build/');
