#!/usr/bin/env node
// Generates the .env values for the PUSU login gate.
//
//   node scripts/gen-login-hash.mjs
//
// Prompts for username + password (input is not stored anywhere) and prints:
//   VITE_LOGIN_USER_SHA256=...   (SHA-256 of the username)
//   VITE_LOGIN_PBKDF2=...        (iterations:saltHex:hashHex — PBKDF2-SHA256)
//
// Paste those two lines into .env (never commit .env) and rebuild.
import { createInterface } from 'node:readline/promises';
import { pbkdf2Sync, randomBytes, createHash } from 'node:crypto';

const ITERATIONS = 600_000; // OWASP 2023+ recommendation for PBKDF2-SHA256

let username, password;
if (process.stdin.isTTY) {
  const rl = createInterface({ input: process.stdin, output: process.stderr });
  username = (await rl.question('Kullanıcı adı: ')).trim();
  password = await rl.question('Şifre: ');
  rl.close();
} else {
  // Piped input: first line = username, second line = password.
  const text = await new Promise((resolve) => {
    let buf = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (c) => { buf += c; });
    process.stdin.on('end', () => resolve(buf));
  });
  [username = '', password = ''] = text.split('\n');
  username = username.trim();
  password = password.replace(/\r$/, '');
}

if (!username || !password) {
  console.error('Kullanıcı adı ve şifre boş olamaz.');
  process.exit(1);
}

const userSha = createHash('sha256').update(username, 'utf8').digest('hex');
const salt = randomBytes(16);
const hash = pbkdf2Sync(password, salt, ITERATIONS, 32, 'sha256');

console.log(`\n# PUSU login — .env içine yapıştırın (asla commit etmeyin)`);
console.log(`VITE_LOGIN_USER_SHA256=${userSha}`);
console.log(`VITE_LOGIN_PBKDF2=${ITERATIONS}:${salt.toString('hex')}:${hash.toString('hex')}`);
