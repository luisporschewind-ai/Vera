// Trusted profile generator only. Never executes the supplied project command.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const root = process.argv[2];
if (!root || !path.isAbsolute(root)) throw new Error('runtime path required');
const meta = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
if (meta.name !== '@anthropic-ai/sandbox-runtime' || meta.version !== '0.0.77') {
  throw new Error('runtime version mismatch');
}
let input = '';
for await (const chunk of process.stdin) {
  input += chunk;
  if (input.length > 1_000_000) throw new Error('input limit');
}
const payload = JSON.parse(input);
if (!Array.isArray(payload.argv) || !payload.argv.length ||
    payload.argv.some(x => typeof x !== 'string' || x.includes('\0'))) {
  throw new Error('invalid argv');
}
if (!Array.isArray(payload.allowMachLookup) ||
    payload.allowMachLookup.some(x => typeof x !== 'string' || x.includes('*'))) {
  throw new Error('invalid Mach service capability');
}
const { wrapCommandWithSandboxMacOS } = await import(
  pathToFileURL(path.join(root, 'dist/sandbox/macos-sandbox-utils.js')).href
);
const quote = value => "'" + value.replaceAll("'", "'\\''") + "'";
if (!/^vera-command-[A-Za-z0-9_-]+$/.test(payload.darwinUserDirSuffix)) {
  throw new Error('invalid temporary directory suffix');
}
const command = wrapCommandWithSandboxMacOS({
  // Restricted system launchers may discard this variable. Set it after the
  // final shell starts, before exec; it names only Core's private temp root.
  command: 'export DIRHELPER_USER_DIR_SUFFIX=' + quote(payload.darwinUserDirSuffix) +
    '; exec ' + payload.argv.map(quote).join(' '),
  commandId: 'vera-command',
  needsNetworkRestriction: true,
  readConfig: payload.readConfig,
  writeConfig: payload.writeConfig,
  allowAllUnixSockets: false,
  allowLocalBinding: false,
  allowPty: false,
  allowGitConfig: false,
  enableWeakerNetworkIsolation: false,
  allowAppleEvents: false,
  allowMachLookup: payload.allowMachLookup,
  binShell: '/bin/bash',
});
process.stdout.write(JSON.stringify({ command }));
