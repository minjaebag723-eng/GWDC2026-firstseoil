# SharePie — AI Settlement Agent (GWDC 2026 Challenge A)

> SharePie is, at its core, an AI Settlement Agent that interprets users' natural-language cost-sharing conditions, calculates and verifies a compliant settlement, locks the approved amounts in escrow, releases them after the hold period, and records the result on-chain. Two optional modules extend it: an AI Shopping Agent for pre-settlement discovery, and an AI Dispute Agent for post-settlement investigation.

> 사용자가 말로 정한 분담 조건과 지출 한도(1인·총 한도, 허용 판매처)를 AI가 해석하고, 코드가 금액을 계산·검증해 규칙을 통과한 경우에만 참여자가 MetaMask로 직접 Ethereum Sepolia 테스트넷 에스크로(ShareLedger)에 테스트 토큰 PieCoin을 예치하며, 위반 시 결제 없이 중단 기록(`Blocked`)이, 이의제기 시 AI 판정과 환불 기록(`DisputeResolved`·`Refunded`)이 온체인에 남는다.

---

## 온체인 증빙 — Ethereum Sepolia 테스트넷 (tx hash + 로그)

테스트넷 전용. 실제 화폐·메인넷은 다루지 않는다. PieCoin(PIE)은 decimals 0의 테스트 토큰(1 PIE = 1원 표시, 실화폐 가치 없음).

| 항목 | 주소 |
|---|---|
| ShareLedger (에스크로·자금추적·이의제기) | [`0xF297240957c3aB10458Dc1A4C6eC2eA18292529E`](https://sepolia.etherscan.io/address/0xF297240957c3aB10458Dc1A4C6eC2eA18292529E) (배포 블록 11801645) |
| PieToken (PieCoin) | [`0xF5cB871A8890bd1D34bf36E749F012D95589E0fD`](https://sepolia.etherscan.io/address/0xF5cB871A8890bd1D34bf36E749F012D95589E0fD) |
| 에이전트(Pie) 지갑 — 등록·중단·판정·환불·지급 서명 (테스트 전용) | [`0x33f446E980bd8F1CeeAEFA43B2FfDB5e45c46C36`](https://sepolia.etherscan.io/address/0x33f446E980bd8F1CeeAEFA43B2FfDB5e45c46C36) |

### 조건 2회 변경 실행 (2026-09-28 22:36 UTC = 09-29 07:36 KST)

같은 조건("진주2는 5천원 적게 내고 나머지 세 명이 나눠줘", 총 35,900원, 4명)으로 실행하고, 지출 한도만 바꿔 다시 실행했다.

| Run | 조건 → 결과 | TxHash (Etherscan) |
|---|---|---|
| **1 정상** | 예산 40,000원 → 코드 계산 [5,225 / 10,225 × 3] → 등록 → 참여자 3명 본인 서명 예치 → 보류 180초 → **지급 `Paid`** | 등록 [`0xb5d5158f…fb60c0`](https://sepolia.etherscan.io/tx/0xb5d5158f878c219c67421af295727c4ee3e3f7c9934e2e925bceffd6e1fb60c0) · 예치 [`0xf55e5561…c5ad0`](https://sepolia.etherscan.io/tx/0xf55e5561095828ffeb8335d70a269386b9709aef71b8471b9ba47aa7badc5ad0) [`0xe9baf799…b9bba`](https://sepolia.etherscan.io/tx/0xe9baf799f3fea594bbd70ba69e10a431f84fddb28df4c735e652a2a490db9bba) [`0xaf31a0ea…4c0ec`](https://sepolia.etherscan.io/tx/0xaf31a0ea5180afda72da2d005172b0592aa4924924ca64d075d1a9c9f0b4c0ec) · 지급 [`0x932d4af1…b4d7c6`](https://sepolia.etherscan.io/tx/0x932d4af1317b1caf49304e2e660585e48c09bf38ba040ef60c3d7d7745b4d7c6) |
| **1.5 조건 변경 ①** | 1인 한도 9,000원 → 코드 `OVER_PERSON_CAP` → 등록·예치·지급 0건, **`Blocked` 기록** (AI 호출 0회) | [`0x4e779d27…6ff5cb`](https://sepolia.etherscan.io/tx/0x4e779d27db4761eacad55636783b3b9482434df50a2e9641aecf7937f86ff5cb) |
| **1.5 조건 변경 ②** | 총 한도 30,000원 → 코드 `OVER_TOTAL_CAP` → **`Blocked` 기록** | [`0x8367cb18…8f33fc`](https://sepolia.etherscan.io/tx/0x8367cb18e439e8e9062a451c1ef15d347032dc576001098b11dae3d5fa8f33fc) |
| **2 이의제기** | 별도 정산 등록 → 3명 예치(`Locked`) → "판매자 품절 취소" 이의제기 → AI 판정 `GENUINE_ERROR` → 코드가 환불 3건 실행 → 판정 기록 → **`Refunded`**, 잔액 전액 복구 | 등록 [`0x8a75d8a5…66890`](https://sepolia.etherscan.io/tx/0x8a75d8a508b63d7a3ef77d536a73374fa30aadb9841be3d70148a19df5d66890) · 이의제기 [`0x156e42e2…738d31`](https://sepolia.etherscan.io/tx/0x156e42e2a5812795f53c214ddf4ce21d7baaf009861b9e0e0ef2a1cc41738d31) · 환불 [`0xfa901750…56f228`](https://sepolia.etherscan.io/tx/0xfa901750cb327e9d40fff252627e9ee1eb99583e769f6abe3faec55a4c56f228) [`0x71715ee7…55b57`](https://sepolia.etherscan.io/tx/0x71715ee7c14b2e2ed0afd94f8110b99f55806f466b84a7d81f7ec52676255b57) [`0xfb6d3acd…06500`](https://sepolia.etherscan.io/tx/0xfb6d3acd7feecee1b170e802d3336e887fb0d0476a65dbb76cdbf8b05c206500) · 판정 [`0x9a217542…3955a3`](https://sepolia.etherscan.io/tx/0x9a217542ee35079eb9b07a4ed33d4f61ecdc8cac3be7f608c86d03805e3955a3) |

### 로그

| 파일 | 내용 |
|---|---|
| [`docs/evidence/sepolia-2026-09-28T22-36-17/summary.md`](docs/evidence/sepolia-2026-09-28T22-36-17/summary.md) | 전체 트랜잭션 표(충전·등록·예치·지급·차단·이의제기·환불·판정) · Kiln 응답 → 행동 기록 · 단계별 AI 토큰 표 |
| [`run1.json`](docs/evidence/sepolia-2026-09-28T22-36-17/run1.json) · [`run1_5.json`](docs/evidence/sepolia-2026-09-28T22-36-17/run1_5.json) · [`run2.json`](docs/evidence/sepolia-2026-09-28T22-36-17/run2.json) | 실행별 원자료 (요청 → AI 응답 → 코드 계산 → 트랜잭션 영수증) |
| [`usage-report.md`](docs/evidence/sepolia-2026-09-28T22-36-17/usage-report.md) | 서버 `GET /api/usage/report.md` 스냅샷 (단계별 Kiln 호출·토큰·지연·에너지 상한) |
| [`docs/evidence/beta-2026-09-29/report.md`](docs/evidence/beta-2026-09-29/report.md) | 베타 참여 집계 보고서 |

**제3자 검증**: 등록 트랜잭션의 `SettlementCreated` 이벤트에 `conditionHash`(조건 원문의 keccak256)·`shares[]`·`purpose`가 있다. `summary.md`의 조건 원문을 `agent/chain.py`의 `condition_hash()`로 해시해 그 값과 대조하면 "그 조건으로 만든 정산"임이 확인된다.

---

## 심사위원이 직접 리뷰할 수 있는 코드

| 파일 | 역할 |
|---|---|
| [`contracts/ShareLedger.sol`](contracts/ShareLedger.sol) | 에스크로·상태 머신(`Open → Locked → Paid / Blocked / Disputed → Refunded`)·이의제기·환불. 참여자 예치는 참여자 본인 서명(`lockForSettlement`), 잔액 부족이면 revert |
| [`contracts/PieToken.sol`](contracts/PieToken.sol) | PieCoin ERC-20 (테스트넷 전용, decimals 0) |
| [`agent/money.py`](agent/money.py) | Stage 2 금액 계산 + 지출 통제 (코드 전용, AI 토큰 0) |
| [`agent/settlement.py`](agent/settlement.py) · [`agent/dispute.py`](agent/dispute.py) | Stage 1/3 AI 해석·설명 · 이의제기 기록 대조(코드) + AI 3분류 판정 + 코드 가드 |
| [`agent/chain.py`](agent/chain.py) | web3.py 체인 어댑터 — AI는 온체인 함수를 직접 부르지 않고, 코드가 AI 응답을 검증한 뒤 호출 |
| [`agent/llm.py`](agent/llm.py) | Kiln API 클라이언트 (단계 태그 · 호출마다 input/output 토큰 기록) |
| [`hardhat/`](hardhat/) | 컨트랙트 테스트 30개(`npm test`) · Sepolia 배포(`npm run deploy -- --network sepolia`) · 위 증거 재현(`npm run evidence`) |

실행: `py -3.14 -m pip install -r requirements.txt` → `.env.example`을 `.env`로 복사해 키 입력 → `py -3.14 -m uvicorn deploy.asgi:app --host 0.0.0.0 --port 8000` (자세한 순서는 [`HOW-TO-RUN.md`](HOW-TO-RUN.md)).
