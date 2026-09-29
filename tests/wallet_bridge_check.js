// 실행: node tests/wallet_bridge_check.js frontend/sp-bridge.js  (Node 18+ · 가상 MetaMask로 지갑 브리지 확인)
// 지갑 브리지를 가상 MetaMask로 실행 — 네트워크 추가 값 · 거절 안내 · 가스 안내 · Faucet
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync(process.argv[2], 'utf8');
let fails = 0; const ok = (c, l) => { console.log((c ? '  ✓ ' : '  ✗ ') + l); if (!c) fails++; };
const CHAIN = { mode: 'bsc', network: 'Ethereum Sepolia Testnet', chain_id: 11155111, chain_id_hex: '0xaa36a7', token: '0x' + 'a'.repeat(40),
  ledger: '0x' + 'b'.repeat(40), token_symbol: 'PIE', token_decimals: 18, explorer: 'https://sepolia.etherscan.io',
  rpc: 'https://ethereum-sepolia-rpc.publicnode.com', native_symbol: 'ETH', faucet: 'https://cloud.google.com/application/web3/faucet/ethereum/sepolia' };
function makeWindow(eth) {
  const store = {};
  const w = { location: { protocol: 'http:', host: 'x', pathname: '/', search: '' }, navigator: { userAgent: 'node', platform: 'x', maxTouchPoints: 0 },
    localStorage: { getItem: k => store[k] || null, setItem: (k, v) => { store[k] = v; } }, ethereum: eth,
    ethers: { BrowserProvider: class { constructor() {} async getSigner() { return { getAddress: async () => '0x' + 'c'.repeat(40) }; } } },
    fetch: async (url) => ({ ok: true, status: 200, json: async () => ({ ok: true, data: url.includes('/api/config') ? { chain: CHAIN, abi: {} } : {} }) }),
    setTimeout, clearTimeout, console };
  w.window = w; w.document = { addEventListener() {} }; w.navigator = w.navigator;
  vm.createContext(w); vm.runInContext(src, w); return w;
}
(async () => {
  console.log('[테스트 네트워크가 숨겨진 MetaMask → 네트워크 추가]');
  let added = null;
  let w = makeWindow({ request: async ({ method, params }) => {
    if (method === 'eth_chainId') return '0x1';
    if (method === 'wallet_switchEthereumChain') { const e = new Error('Unrecognized chain ID'); e.code = 4902; throw e; }
    if (method === 'wallet_addEthereumChain') { added = params[0]; return null; }
    return null; } });
  const addr = await w.SP.web3.connect();
  ok(addr && added, '연결 성공 · 네트워크 추가 요청을 보냄');
  ok(added && added.chainId === '0xaa36a7' && added.chainName === 'Ethereum Sepolia Testnet', `체인: ${added && added.chainName} (${added && added.chainId})`);
  ok(added && added.nativeCurrency.symbol === 'ETH' && !JSON.stringify(added).includes('BNB'), `가스 화폐: ${added && added.nativeCurrency.symbol} (BNB 흔적 없음)`);
  ok(w.SP.web3.faucetUrl === CHAIN.faucet, `Faucet: ${w.SP.web3.faucetUrl}`);

  console.log('[MetaMask가 추가를 거절 (원래 있는 네트워크)]');
  w = makeWindow({ request: async ({ method }) => {
    if (method === 'eth_chainId') return '0x1';
    if (method === 'wallet_switchEthereumChain') { const e = new Error('Unrecognized chain ID'); e.code = 4902; throw e; }
    if (method === 'wallet_addEthereumChain') { const e = new Error('Chain ID already exists'); e.code = -32602; throw e; }
    return null; } });
  try { await w.SP.web3.connect(); ok(false, '거절인데 연결됨'); }
  catch (e) { ok(e.code === 'WRONG_NETWORK' && e.message.includes('Ethereum Sepolia Testnet'), `안내: ${e.message}`); }

  console.log('[사용자가 네트워크 추가를 취소]');
  w = makeWindow({ request: async ({ method }) => {
    if (method === 'eth_chainId') return '0x1';
    if (method === 'wallet_switchEthereumChain') { const e = new Error('Unrecognized chain ID'); e.code = 4902; throw e; }
    if (method === 'wallet_addEthereumChain') { const e = new Error('User rejected the request.'); e.code = 4001; throw e; }
    return null; } });
  try { await w.SP.web3.connect(); ok(false, '취소인데 연결됨'); }
  catch (e) { ok(e.code === 'USER_REJECTED', `취소 안내: ${e.message}`); }

  console.log('[가스가 부족할 때]');
  w = makeWindow({ request: async ({ method }) => {
    if (method === 'eth_requestAccounts') { const e = new Error('insufficient funds for gas * price + value'); throw e; }
    return null; } });
  try { await w.SP.web3.connect(); ok(false, '가스 부족인데 연결됨'); }
  catch (e) { ok(e.code === 'NO_GAS' && e.message.includes('ETH') && !e.message.includes('BNB') && e.message.includes('보내 줘요'), `안내: ${e.message}`); }
  console.log(fails ? `\n✗ 실패 ${fails}건` : '\n✓ 전체 통과'); process.exit(fails ? 1 : 0);
})().catch(e => { console.log('✗ 실행 오류', e); process.exit(1); });
