"""지갑 전체 흐름 검사 — 로컬 체인(anvil)에 컨트랙트를 새로 배포하고, 서버를 실제 체인 모드로 띄운 뒤
화면 지갑 코드(sp-bridge.js)를 Node에서 그대로 돌린다 (MetaMask 자리에 로컬 체인 지갑).

  1) anvil (127.0.0.1:8545)   2) npm install ethers@6 --prefix <폴더>   3) python tests/wallet_e2e_check.py --ethers <폴더>
Sepolia·실제 데이터에는 아무것도 보내지 않아요 (chain id 31337·1337만).
"""
import argparse, importlib.util, os, subprocess, sys, tempfile, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser(); ap.add_argument("--ethers", default="/tmp/ethers6"); ap.add_argument("--rpc", default="http://127.0.0.1:8545"); ap.add_argument("--port", default="8123")
a = ap.parse_args()
spec = importlib.util.spec_from_file_location("clc", ROOT / "tests" / "chain_local_check.py"); clc = importlib.util.module_from_spec(spec); spec.loader.exec_module(clc)
from web3 import Web3
w3 = Web3(Web3.HTTPProvider(a.rpc)); cid = w3.eth.chain_id
if cid not in (31337, 1337):
    sys.exit(f"chain id {cid} — 로컬 테스트 노드에서만")
w3.provider.make_request("evm_setIntervalMining", [0]); w3.provider.make_request("evm_setAutomine", [True])
agent = w3.eth.account.from_key(clc.KEYS[0]); fee = {"maxFeePerGas": w3.to_wei(3, "gwei"), "maxPriorityFeePerGas": w3.to_wei(1, "gwei")}
def send(fn):
    tx = fn.build_transaction({"from": agent.address, **fee}); tx.update({"nonce": w3.eth.get_transaction_count(agent.address, "pending"), "chainId": cid})
    return w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(agent.sign_transaction(tx).raw_transaction), timeout=60)
art = clc.artifacts(); addr = {}
for n in ("PieToken", "ShareLedger"):
    addr[n] = send(w3.eth.contract(abi=art[n]["abi"], bytecode=art[n]["bin"]).constructor())["contractAddress"]
send(w3.eth.contract(address=addr["PieToken"], abi=art["PieToken"]["abi"]).functions.setMinter(agent.address, True))
send(w3.eth.contract(address=addr["ShareLedger"], abi=art["ShareLedger"]["abi"]).functions.setDisputeWindow(6))
w3.provider.make_request("evm_setAutomine", [False]); w3.provider.make_request("evm_setIntervalMining", [1])
print(f"로컬 체인 {cid} · PieToken {addr['PieToken'][:10]}… · ShareLedger {addr['ShareLedger'][:10]}… · 블록 1초 · 이의제기 6초")
env = {**os.environ, "CHAIN_MODE": "bsc", "BSC_RPC_URL": a.rpc, "BSC_CHAIN_ID": str(cid), "BSC_EXPLORER": "", "AGENT_PRIVATE_KEY": clc.KEYS[0],
       "LEDGER_ADDRESS": addr["ShareLedger"], "TOKEN_ADDRESS": addr["PieToken"], "LEDGER_DEPLOY_BLOCK": "0", "DATA_DIR": tempfile.mkdtemp(prefix="sp-wallet-"),
       "LLM_MODE": "mock", "KILN_API_KEY": "", "SERPER_API_KEY": "", "SERPAPI_API_KEY": "", "CHARGE_COOLDOWN_SEC": "0", "CHAIN_WATCH_SEC": "2",
       "DISPUTE_WINDOW_SEC": "6", "CHAIN_MAX_GAS_GWEI": "3", "BETA_ENABLED": "0", "PUBLIC_BASE_URL": ""}
srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "deploy.asgi:app", "--port", a.port, "--log-level", "warning"], cwd=ROOT, env=env)
try:
    base = f"http://127.0.0.1:{a.port}"
    for _ in range(60):
        try:
            if httpx.get(base + "/api/config", timeout=2).status_code == 200: break
        except Exception: pass
        time.sleep(0.5)
    rc = subprocess.run(["node", str(ROOT / "tests" / "wallet_e2e_bridge.cjs"), base, a.rpc, a.ethers], cwd=ROOT).returncode
finally:
    srv.terminate(); srv.wait(timeout=10)
sys.exit(rc)
