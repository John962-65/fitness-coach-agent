#!/usr/bin/env node
// M6.4-B B2/B3：GLB → three.js 加载冒烟测试（生产同路径 GLTFLoader + AnimationMixer）。
// 动作无关口径：
//  1) 循环一致（首帧 ≈ 尾帧：根骨骼与器械）；
//  2) 动画确实驱动骨骼/器械（任一关节或器械行程 ≥ 0.15m）；
//  3) 双脚踝全程静止（位移 ≤ 3mm，贴地不滑移）；
//  4) 手部关节贴合对应器械（杠铃：握点在杆轴上；哑铃：贴合所属铃体）。
// 失败退出码非 0。
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const nm = (p) => pathToFileURL(join(here, '..', 'frontend', 'node_modules', p)).href;
const THREE = await import(nm('three/build/three.module.js'));
const { GLTFLoader } = await import(nm('three/examples/jsm/loaders/GLTFLoader.js'));

const file = process.argv[2];
if (!file) { console.error('用法: node tools/smoke_glb.mjs <file.glb>'); process.exit(2); }

const gltf = await new Promise((res, rej) => {
  new GLTFLoader().parse(readFileSync(file).buffer.slice(0), '', res, rej);
});
const root = gltf.scene;
root.updateMatrixWorld(true);
const clip = gltf.animations[0];
if (!clip) { console.error('无动画'); process.exit(1); }

const byName = {};
const equipNodes = [];
root.traverse((o) => {
  if (o.name) byName[o.name] = o;
  if (/barbell|dumbbell/.test(o.name) && o.isObject3D && !o.isBone) equipNodes.push(o);
});
if (!equipNodes.length) { console.error('未找到器械节点'); process.exit(1); }

const mixer = new THREE.AnimationMixer(root);
const action = mixer.clipAction(clip);
action.play();
const duration = clip.duration;
const sampleTs = [0, duration * 0.15, duration * 0.28, duration * 0.53,
  duration * 0.66, duration * 0.8, duration];
const frames = sampleTs.map((t) => {
  mixer.setTime(t);
  root.updateMatrixWorld(true);
  const joints = {};
  for (const n of ['Hips', 'LeftLeg', 'LeftFoot', 'LeftHand', 'RightLeg',
    'RightFoot', 'RightHand', 'LeftArm', 'RightArm', 'Head']) {
    if (byName[n]) joints[n] = new THREE.Vector3().setFromMatrixPosition(byName[n].matrixWorld);
  }
  const equip = {};
  for (const e of equipNodes) {
    equip[e.name] = new THREE.Vector3().setFromMatrixPosition(e.matrixWorld);
  }
  return { t, joints, equip };
});

let failed = false;
const fail = (msg) => { console.error('✗ ' + msg); failed = true; };

// 1) 循环一致
const j0 = frames[0].joints, jN = frames[frames.length - 1].joints;
if (j0.Hips.distanceTo(jN.Hips) > 1e-3) fail('循环一致(Hips)');
for (const e of equipNodes) {
  if (frames[0].equip[e.name].distanceTo(frames[frames.length - 1].equip[e.name]) > 1e-3)
    fail(`循环一致(${e.name})`);
}

// 2) 动画驱动：任一关节/器械行程
let travel = 0, what = '';
for (const n of Object.keys(j0)) {
  const tr = Math.max(...frames.map((f) => f.joints[n].distanceTo(j0[n])));
  if (tr > travel) { travel = tr; what = n; }
}
for (const e of equipNodes) {
  const tr = Math.max(...frames.map((f) => f.equip[e.name].distanceTo(frames[0].equip[e.name])));
  if (tr > travel) { travel = tr; what = e.name; }
}
if (travel < 0.15) fail(`动画行程不足: ${what} ${travel.toFixed(3)}m`);

// 3) 双脚踝全程静止（贴地不滑移）
for (const foot of ['LeftFoot', 'RightFoot']) {
  for (const f of frames) {
    if (f.joints[foot].distanceTo(j0[foot]) > 3e-3)
      fail(`${foot} 滑移: ${f.joints[foot].distanceTo(j0[foot]).toFixed(4)}m @t=${f.t.toFixed(2)}`);
  }
}

// 4) 手贴合器械：每只手找最近器械节点
//    杠铃 → 手应在杆轴上（y/z 与杆心一致）；哑铃 → 全轴贴合
const handEquip = {};
for (const hand of ['LeftHand', 'RightHand']) {
  let best = null, bd = 1e9;
  for (const e of equipNodes) {
    const d = Math.hypot(
      frames[0].joints[hand].x - frames[0].equip[e.name].x,
      frames[0].joints[hand].y - frames[0].equip[e.name].y,
      frames[0].joints[hand].z - frames[0].equip[e.name].z);
    if (d < bd) { bd = d; best = e.name; }
  }
  handEquip[hand] = best;
}
for (const f of frames) {
  for (const [hand, eq] of Object.entries(handEquip)) {
    const h = f.joints[hand], e = f.equip[eq];
    const d = eq.startsWith('barbell')
      ? Math.hypot(h.y - e.y, h.z - e.z)          // 握点在杆轴上（x 偏移为握距）
      : h.distanceTo(e);                          // 哑铃贴合铃心
    if (d > 8e-3) fail(`${hand} 脱离 ${eq}: Δ=${d.toFixed(4)} @t=${f.t.toFixed(2)}`);
  }
}

console.log(`动画「${clip.name}」 ${duration.toFixed(2)}s；最大行程 ${what} ` +
  `${travel.toFixed(3)}m；器械 [${equipNodes.map((e) => e.name).join(', ')}]；` +
  `${failed ? '冒烟失败' : '冒烟通过 ✓'}`);
process.exit(failed ? 1 : 0);
