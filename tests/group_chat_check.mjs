// 그룹 정산방 재현 테스트 — 폰 3대가 같은 방에서 대화
// (메시지 중복·순서 / Pie 끼어들기·무응답 / 확인 카드·버튼 / 입력창)
// 실행: 백엔드를 켠 뒤  API=http://127.0.0.1:8000 node tests/group_chat_check.mjs
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const html = fs.readFileSync(path.join(ROOT, 'frontend/index.html'), 'utf8');
const bridge = fs.readFileSync(path.join(ROOT, 'frontend/sp-bridge.js'), 'utf8');
const src = html.split('<script type="text/x-dc" data-dc-script>')[1].split('</script>')[0];
const BASE = process.env.API || 'http://127.0.0.1:8000';
const RUN = Date.now().toString(36).slice(-5);
let failures = 0;
const ok = (cond, msg) => { console.log((cond ? '  ✓ ' : '  ✗ ') + msg); if (!cond) failures++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));

function makePhone(opts = {}) {
  const store = opts.store || {};
  const loc = { protocol: 'http:', host: 'localhost:8000', pathname: '/', href: '', origin: 'http://localhost:8000', search: '' };
  const win = { SP_API_BASE: BASE, location: loc, localStorage: { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = String(v); } },
    addEventListener() {}, removeEventListener() {}, isSecureContext: true, innerHeight: 900, innerWidth: 420, open() {} };
  const ctx = vm.createContext({ window: win, fetch, console, setTimeout, clearTimeout, setInterval: () => 0, clearInterval() {},
    navigator: { userAgent: 'node', ...(opts.geo ? { geolocation: opts.geo } : {}) }, location: loc, localStorage: win.localStorage, URLSearchParams, JSON, Date, Math, Promise, BigInt, Proxy, Set, Map });
  ctx.window.window = ctx.window;
  vm.runInContext(bridge.replace('(function () {', '(function () { var location = window.location;'), ctx);
  ctx.SP = ctx.window.SP;
  class StreamableLogic {
    constructor(props) { this.props = props || {}; this.state = {}; }
    setState(u, cb) { const p = typeof u === 'function' ? u(this.state) : u; this.state = { ...this.state, ...(p || {}) }; cb && cb(); }
  }
  const Component = vm.runInContext(`(function(DCLogic, StreamableLogic, React){ ${src}\n; return Component; })`, ctx)(StreamableLogic, StreamableLogic, { createRef: () => ({ current: null }) });
  const c = new Component({});
  c.toasts = []; c.showToast = t => { c.toasts.push(t); };
  c._store = store; c._loc = loc; c.SP = ctx.SP;
  return c;
}


async function main() {
  const names = [['가나' + RUN, 'ga'], ['다라' + RUN, 'na'], ['마바' + RUN, 'da']];
  const P = names.map(() => makePhone());
  for (const [i, p] of P.entries()) {
    await p.boot();
    Object.assign(p.state, { authMode: 'signup', name: names[i][0], email: `${names[i][1]}.${RUN}@gc.test`, pw: 'abc12345', signupId: `${names[i][1]}${RUN}` });
    await p.sendSignupCode(); await p.submitAuth();
  }
  const [A, B, C] = P;
  ok(P.every(p => p.state.screen === 'main'), '폰 3대 가입: ' + P.map(p => p.me).join(', '));
  const gid = 'gq' + RUN;
  await A.SP.api('/api/groups/create', { id: gid, name: 'QA 정산방', members: [A.me, B.me, C.me] });
  await A.refreshServer(); await B.acceptInvite(gid); await C.acceptInvite(gid);
  const G = p => p.state.groups.find(x => x.id === gid);
  const server = async () => (await A.SP.api('/api/groups')).find(r => r.id === gid);
  const say = async (p, text) => { p.state.gchatId = gid; p.state.gchatInput = text; await p.sendGchat(); };
  const refreshAll = async () => { for (const p of P) { p._polling = false; await p.refreshServer(); } };
  const ids = arr => arr.filter(m => m.text || m.kind).map(m => m.id);

  console.log('[1. 메시지 중복 · 순서]');
  await Promise.all([say(A, '안녕 나 도착'), say(B, '나도 거의 다 왔어')]);
  await say(A, '어디 앉을까');
  await refreshAll();
  const sv = await server();
  const svIds = ids(sv.msgs);
  for (const p of P) {
    const mine = ids(G(p).msgs);
    const dup = mine.filter((x, i) => mine.indexOf(x) !== i);
    ok(!dup.length, `${p.me}: 중복 메시지 없음 ${dup.length ? '(중복 ' + dup.length + '개)' : ''}`);
    const common = mine.filter(x => svIds.includes(x));
    ok(JSON.stringify(common) === JSON.stringify(svIds.filter(x => common.includes(x))), `${p.me}: 서버와 같은 순서 → ${G(p).msgs.filter(m => m.text && !m.pie && !m.guide).map(m => m.text.slice(0, 6)).join(' / ')}`);
  }

  console.log('[2. Pie가 끼어들기 · 답하기]');
  const pieAfter = async (p, text) => { const before = G(p).msgs.length; await say(p, text); await sleep(150); return G(p).msgs.slice(before).filter(m => m.pie || (m.from === 'sys' && m.replyTo)); };
  for (const t of ['2시에 보자', '나 5분 늦어', '3번 출구 앞이야', 'ㅋㅋ 오늘 1등 했다', '배고프다']) {
    const r = await pieAfter(B, t);
    ok(!r.length, `잡담 '${t}' → Pie ${r.length ? '끼어듦: ' + r[0].text.slice(0, 40) : '조용함'}`);
  }
  for (const t of ['파이', 'Pie 있어?', '파이야 도와줘', '파메 정산 어떻게 해?', '@파이 누가 안 냈어']) {
    const r = await pieAfter(C, t);
    ok(r.length > 0, `부르기 '${t}' → ${r.length ? 'Pie: ' + r[0].text.slice(0, 40) : '답 없음'}`);
  }

  console.log('[3. 확인 카드 · 버튼]');
  await say(A, '파이야 3만원 셋이 똑같이 나눠');
  let card = G(A).msgs.filter(m => m.kind === 'confirm').at(-1);
  ok(!!card, '확인 카드 생김');
  await refreshAll();
  for (const p of [B, C]) ok(G(p).msgs.filter(m => card && m.id === card.id).length === 1, `${p.me} 폰에도 확인 카드 1개`);
  if (card) {
    await Promise.all([A.confirmSettlement(gid, card.id), A.confirmSettlement(gid, card.id), B.confirmSettlement(gid, card.id)]);
    await sleep(300); await refreshAll();
    const s2 = await server();
    const reqs = s2.msgs.filter(m => m.kind === 'splitReq');
    ok(reqs.length === 1, `확인을 빠르게 두 번 + 다른 사람도 누름 → 승인 요청 카드 ${reqs.length}개 (1개여야 함)`);
    const sysDup = s2.msgs.filter(m => m.from === 'sys' && m.text && !m.pie).map(m => m.text).filter((x, i, a) => a.indexOf(x) !== i);
    ok(!sysDup.length, `같은 안내 메시지 중복 없음 ${sysDup.length ? '(' + sysDup[0].slice(0, 30) + '…)' : ''}`);
    for (const p of P) ok((G(p).msgs.find(m => m.id === card.id) || {}).resolved === true, `${p.me} 폰: 확인 카드가 '처리됨'`);
    ok(P.every(p => JSON.stringify((G(p).splitApproval || {}).id) === JSON.stringify((s2.splitApproval || {}).id)), '세 폰의 승인 요청 상태가 서버와 같음');
  }

  console.log('[4. 입력창]');
  B.state.gchatId = gid; B.state.gchatInput = '입력창 확인';
  await B.sendGchat();
  ok(B.state.gchatInput === '' && B.state.pieWait !== gid, `보낸 뒤 입력창 비움 · 'Pie 입력 중' 꺼짐`);
  console.log(failures ? `\n✗ 실패 ${failures}건` : '\n✓ 전체 통과');
  process.exit(failures ? 1 : 0);
}
main().catch(e => { console.log('  ✗ 실행 오류:', e && (e.stack || e)); process.exit(1); });
