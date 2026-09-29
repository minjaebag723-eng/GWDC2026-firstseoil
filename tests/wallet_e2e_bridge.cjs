// 지갑 전체 흐름 — 화면 지갑 코드(frontend/sp-bridge.js)를 그대로 실행하고, MetaMask 자리에 로컬 체인(anvil) 지갑을 넣는다.
// tests/wallet_e2e_check.py가 서버·체인을 띄운 뒤 부른다:  node tests/wallet_e2e_bridge.cjs <서버> <RPC> <ethers 폴더>
const fs = require('fs'), vm = require('vm'), path = require('path');
const [, , SERVER, RPC, ETHERS_DIR] = process.argv;
const ethers = require(path.join(ETHERS_DIR, 'node_modules', 'ethers'));
const SRC = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'sp-bridge.js'), 'utf8');
let fails = 0;
const ok = (c, l) => { console.log((c ? '  ✓ ' : '  ✗ ') + l); if (!c) fails++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const rpc = async (method, params = []) => {
  const r = await fetch(RPC, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }) });
  const d = await r.json(); if (d.error) { const e = new Error(d.error.message); e.code = d.error.code; e.data = d.error.data; throw e; } return d.result;
};
// MetaMask 흉내 (EIP-1193): 계정 요청·네트워크 전환은 지갑이, 나머지는 로컬 체인이 처리 (서명은 anvil의 잠금 해제·가장 계정)
function metamask(addr, opt = {}) {
  return { isMetaMask: true, on() {}, removeListener() {}, request: async ({ method, params }) => {
    if (method === 'eth_requestAccounts' || method === 'eth_accounts') return [addr];
    if (method === 'eth_chainId' && opt.chainId) return opt.chainId;
    if (method === 'wallet_switchEthereumChain') {
      if (opt.rejectSwitch) { const e = new Error('Unrecognized chain ID'); e.code = 4902; throw e; }
      return null;
    }
    if (method === 'wallet_addEthereumChain') { if (opt.rejectAdd) { const e = new Error('Chain already exists'); e.code = -32602; throw e; } return null; }
    if (method === 'wallet_watchAsset') return true;
    return rpc(method, params || []);
  } };
}
function page(eth) {
  const store = {};
  const w = { location: { protocol: 'http:', host: 'localhost', origin: SERVER, pathname: '/', search: '', href: SERVER + '/' },
    navigator: { userAgent: 'node', platform: 'x', maxTouchPoints: 0 },
    localStorage: { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } },
    sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    ethereum: eth, ethers, fetch: (u, o) => fetch(/^https?:/.test(u) ? u : SERVER + u, o),
    setTimeout, clearTimeout, setInterval, clearInterval, console, URL, URLSearchParams };
  w.window = w; w.self = w; w.document = { addEventListener() {}, visibilityState: 'visible' };
  vm.createContext(w); vm.runInContext(SRC, w); return w;
}
const api = async (p, body, tok) => {
  const r = await fetch(SERVER + p, { method: body ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json', ...(tok ? { Authorization: 'Bearer ' + tok } : {}) }, body: body ? JSON.stringify(body) : undefined });
  const d = await r.json().catch(() => ({})); if (r.status >= 400) throw new Error(`${r.status} ${JSON.stringify(d).slice(0, 200)}`); return d.data ?? d;
};
const rnd = () => Math.random().toString(36).slice(2, 8);
async function user(name) {
  const email = `w.${rnd()}@wallet.test`; const c = await api('/api/auth/email-code', { email, purpose: 'signup' });
  return api('/api/auth/signup', { name, email, password: 'Qa' + rnd() + rnd() + '9', code: c.dev_code, pie_id: 'w' + rnd() });
}

(async () => {
  const A = await user('지갑가'), B = await user('지갑나');
  const aAddr = (await rpc('eth_accounts'))[6];                      // 가: ETH가 있는 로컬 계정
  const bAddr = ethers.Wallet.createRandom().address;                 // 나: ETH 0인 새 지갑 (가스 자동 지급 확인)
  await rpc('anvil_impersonateAccount', [bAddr]);
  const pa = page(metamask(aAddr)), pb = page(metamask(bAddr));
  pa.SP.setToken(A.token); pb.SP.setToken(B.token);

  console.log('[1. 지갑 연결 — 화면 지갑 코드 그대로]');
  const gotA = await pa.SP.web3.connect(), gotB = await pb.SP.web3.connect();
  ok(gotA.toLowerCase() === aAddr.toLowerCase() && gotB.toLowerCase() === bAddr.toLowerCase(), `connect() → ${gotA.slice(0, 8)}… · ${gotB.slice(0, 8)}…`);
  const pw = page(metamask(aAddr, { chainId: '0x1', rejectSwitch: true, rejectAdd: true })); pw.SP.setToken(A.token);
  try { await pw.SP.web3.connect(); ok(false, '다른 네트워크인데 연결됨'); } catch (e) { ok(e.code === 'WRONG_NETWORK', `다른 네트워크·추가 거절 → 안내: ${e.message.slice(0, 60)}…`); }

  console.log('[2. 지갑 등록 → 가스 자동 지급]');
  const ra = await pa.SP.api('/api/members/register', { name: A.short, wallet: gotA });
  const rb = await pb.SP.api('/api/members/register', { name: B.short, wallet: gotB });
  ok(rb.wallet && rb.gas && rb.gas.pending, `새 지갑 등록 → 가스 보내는 중 (gas=${JSON.stringify(rb.gas)})`);
  let bal = 0n; const t0 = Date.now();
  while (Date.now() - t0 < 45000 && (bal = BigInt(await rpc('eth_getBalance', [bAddr, 'latest']))) === 0n) await sleep(500);
  ok(bal > 0n, `가스 도착 ${ethers.formatEther(bal)} ETH (${((Date.now() - t0) / 1000).toFixed(1)}초)`);

  console.log('[3. 충전]');
  const ca = await pa.SP.api('/api/wallet/charge', { name: A.short }); const cb = await pb.SP.api('/api/wallet/charge', { name: B.short });
  ok(ca.amount > 0 && cb.amount > 0 && cb.wallet && cb.wallet.balance >= cb.amount, `PIE 충전 ${cb.amount} · 나의 잔액 ${cb.wallet && cb.wallet.balance}`);

  console.log('[4. 정산 등록 → 결제(승인 + 예치 서명) → 자동 지급]');
  const p = await pa.SP.api('/api/settlement/request', { group_name: '지갑 점검', members: [A.short, B.short], shares: [[A.short, 6000], [B.short, 6000]],
    total: 12000, payer: A.short, rule_text: '1만2천원 둘이', purpose: '지갑 점검' });
  const sid = p.id || (p.settlement && p.settlement.id);
  let rec = await pa.SP.api(`/api/settlement/${sid}`);
  ok(rec.status === 'open' && rec.chainId, `정산 등록 → ${rec.status} (${sid})`);
  const states = Object.fromEntries(rec.members.map(m => [m.name, m.state]));
  ok(states[A.short] !== 'wait' && states[B.short] === 'wait', `멤버 상태: 결제자 ${A.short}=${states[A.short]} · ${B.short}=${states[B.short]}`);
  try { await pa.SP.web3.payShare(rec, A.short, () => {}); ok(false, '결제자가 예치함'); }
  catch (e) { ok(e.code === 'IS_PAYER', `결제자가 누르면 트랜잭션 없이 안내: ${e.message}`); }
  for (const [pg, who] of [[pb, B.short]].filter(([, w]) => states[w] === 'wait')) {
    const steps = [];
    const r = await pg.SP.web3.payShare(rec, who, s => steps.push(s));
    rec = await pg.SP.api('/api/settlement/approve', { settlement_id: sid, name: who, tx_hash: r.txHash });
    ok(/^0x[0-9a-f]{64}$/i.test(r.txHash), `${who} 결제 tx ${r.txHash.slice(0, 12)}… · 안내 ${steps.length}단계 ('${steps[0] || ''}')`);
  }
  ok(rec.status === 'locked', `대기 중인 멤버 모두 예치 → ${rec.status}`);
  try { await pb.SP.web3.payShare(rec, B.short, () => {}); ok(false, '두 번 결제됨'); }
  catch (e) { ok(e.code === 'ALREADY_PAID', `이미 낸 사람이 또 누르면 → ${e.message}`); }
  const t1 = Date.now();
  while (Date.now() - t1 < 45000 && rec.status !== 'paid') { await sleep(1000); rec = await pa.SP.api(`/api/settlement/${sid}`); }
  ok(rec.status === 'paid' && (rec.txs || []).some(x => x.kind === 'release'), `이의제기 기간 뒤 자동 지급 → ${rec.status} (${((Date.now() - t1) / 1000).toFixed(0)}초)`);

  console.log('[5. 오류 안내]');
  const px = page(metamask((await rpc('eth_accounts'))[7])); px.SP.setToken(B.token);
  const p2 = await pa.SP.api('/api/settlement/request', { group_name: '계정 점검', members: [A.short, B.short], shares: [[A.short, 1000], [B.short, 1000]], total: 2000, payer: A.short, rule_text: '2천원 둘이', purpose: '점검' });
  const rec2 = await pa.SP.api(`/api/settlement/${p2.id || (p2.settlement && p2.settlement.id)}`);
  try { await px.SP.web3.payShare(rec2, B.short, () => {}); ok(false, '다른 계정인데 결제됨'); } catch (e) { ok(e.code === 'WRONG_ACCOUNT', `MetaMask 계정이 다르면 → ${e.message}`); }
  console.log(fails ? `\n✗ 실패 ${fails}건` : '\n✓ 전체 통과'); process.exit(fails ? 1 : 0);
})().catch(e => { console.log('  ✗ 실행 오류:', e && (e.stack || e.message || e)); process.exit(1); });
