#!/usr/bin/env node
// M6.4-B B2.3：GLB 校验（Khronos gltf-validator）。
// 用法：node tools/validate_glb.mjs <file.glb> [more.glb ...]
// 退出码 0 = 无错误（告警仍列出，供人工判断）；非 0 = 有错误或用法问题。
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
let validateBytes;
try {
  ({ validateBytes } = await import('gltf-validator'));
} catch {
  // gltf-validator 安装在 frontend/node_modules（前端 devDependencies）
  const p = join(here, '..', 'frontend', 'node_modules', 'gltf-validator',
    'index.js');
  ({ validateBytes } = await import(pathToFileURL(p).href));
}

const files = process.argv.slice(2);
if (!files.length) {
  console.error('用法: node tools/validate_glb.mjs <file.glb> [more.glb ...]');
  process.exit(2);
}
let failed = false;
for (const f of files) {
  const bytes = new Uint8Array(readFileSync(f));
  const r = await validateBytes(bytes, {
    maxIssues: 50,
    externalResourceFunction: async () => new Uint8Array(0),
  });
  const errs = (r.issues.messages || []).filter((m) => m.severity === 0);
  const warns = (r.issues.messages || []).filter((m) => m.severity === 1);
  const info = JSON.parse(
    new TextDecoder().decode(bytes.slice(20, 20 + Number(
      new DataView(bytes.buffer, bytes.byteOffset).getUint32(12, true))))
  );
  const anims = (info.animations || []).map((a) => a.name);
  const joints = info.skins?.[0]?.joints?.length ?? 0;
  if (errs.length) failed = true;
  console.log(`${f}`);
  console.log(`  validator: ${errs.length} errors, ${warns.length} warnings; ` +
    `${info.meshes?.length ?? 0} meshes, ${joints} joints, animations=[${anims.join(', ')}]`);
  for (const m of [...errs, ...warns]) {
    console.log(`  [${m.severity === 0 ? 'ERROR' : 'WARN '}] ${m.code} ${m.message}`);
  }
}
process.exit(failed ? 1 : 0);
