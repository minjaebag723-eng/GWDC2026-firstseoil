# TASK — SharePie 실행 체크리스트

우선순위 순서대로 나열. 위에서부터 순서대로 처리하고, 순서를 건너뛰지 않는다. (`CLAUDE.md` 2번의 개발 순서 원칙과 동일)

> UI/UX 화면 제작은 별도 담당자가 이미 진행 중이므로 이 체크리스트에는 포함하지 않는다. 여기서는 **AI 로직·백엔드·블록체인**만 다루고, 완성되는 대로 기존 화면에 "연결"만 한다.

## Phase 0 — 착수 (0~4h)

- [ ] (전체) `START.md` 1~5번 세팅 완료
- [ ] (전체) `CLAUDE.md` 1번(선언 위계) 함께 확인 — 정산이 유일한 메인이라는 구조 재확인
- [ ] (백엔드) Kiln API `curl` 테스트 성공, `usage` 토큰 값 확인
- [ ] (블록체인 담당) 체인 확정 + devnet 컨트랙트 골격 배포(빈 함수라도 컴파일·배포 성공)
- [ ] (UI/UX 담당과 조율) 화면에서 호출할 API 요청/응답 스키마를 서로 확인하고 고정

## Phase 1 — 정산 코어 + PieCoin 블록체인 (4~20h) ★최우선, 이것만으로도 데모 성립

### 백엔드 (AI·로직)
- [ ] `POST /settlement/analyze` — Kiln API Stage1 연동, 자연어→JSON 구조화
- [ ] **다턴(multi-turn) 처리** — 사용자가 조건을 도중에 수정하면 Stage1이 최신 JSON을 다시 생성해 Stage2로 넘기는 구조 구현 (`CLAUDE.md` 3번 참고)
- [ ] `POST /settlement/calculate` — 순수 코드 계산 로직 (Kiln 호출 없음)
- [ ] `POST /settlement/explain` — Kiln API Stage3 연동
- [ ] 각 호출마다 Stage 태그(`settlement.analyze` 등) + 토큰 수 로깅

### 블록체인
- [ ] `charge_token` 구현 — PieCoin 발급
- [ ] `lock_for_settlement` 구현 — **잔액 부족 시 잠금 거부하는 검증 로직 필수 포함** (`CLAUDE.md` 5번, 11번 참고)
- [ ] `release_to_recipient` 구현 — 전원 승인 완료 시에만 지급되도록 조건 검증
- [ ] 백엔드에서 위 3개 함수를 SDK로 호출하는 연동 코드 작성

### 프론트 연결
- [ ] 정산방 생성 화면 → `POST /settlement/analyze` 연동
- [ ] 정산 결과 화면 → `POST /settlement/calculate`, `/explain` 응답 반영
- [ ] 승인 화면 → `POST /settlement/approve` 연동, 지갑 서명 흐름 확인

### 완료 기준
- [ ] **Run 1 시나리오(정상 정산)가 처음부터 끝까지 한 번에 성공** — 조건입력→계산→승인→온체인기록→TxHash 확인
- [ ] **잔액 부족 케이스 테스트** — 일부러 잔액 부족한 지갑으로 시도해서 정산이 정상적으로 막히는지 확인

## Phase 2 — Dispute 모듈 연결 (20~30h) — 정산 코어에 꽂는 확장

### 백엔드
- [ ] `POST /dispute/raise` — `raise_dispute` 컨트랙트 함수 연동
- [ ] `POST /dispute/investigate` — 전체 로그 취합 후 Kiln API 호출(`dispute.investigate` 태그), 3분류(`CLAUDE.md` 7번) 판정 프롬프트
- [ ] `POST /dispute/resolve` — 판정 결과에 따라 `resolve_dispute` + `refund_participant` 자동 호출

### 블록체인
- [ ] `raise_dispute`, `resolve_dispute`, `refund_participant` 구현

### 프론트 연결
- [ ] 이의제기 접수 화면 → `POST /dispute/raise` 연동
- [ ] 이의제기 결과 화면 → `POST /dispute/investigate`, `/resolve` 응답 반영

### 완료 기준
- [ ] **Run 2 시나리오(이의제기)가 성공** — Run 1 결과에 이의제기 → 판정 → 자동 처리까지 확인

## Phase 3 — 기술 로그 & 증빙 (30~34h)

- [ ] (백엔드) Kiln 호출별 input/output 토큰, 계산 로그, 온체인 기록을 조회 API로 제공
- [ ] (프론트 연결) 기술 로그 화면에 위 데이터 바인딩
- [ ] Run 1 / Run 2 각각의 로그를 스크린샷/캡처 가능하게 정리

## Phase 4 — 결제방식 분기 (34~38h, 시간 되면)

- [ ] (블록체인) `mark_offline_payment` 구현
- [ ] (백엔드) `POST /settlement/offline-payment` 연동
- [ ] (프론트 연결) 결제방식 선택 화면 → 위 API 연동

## Phase 5 — Shopping 모듈 추가 (38~44h, 시간 남으면만) — 없어도 서비스는 완성된 상태

- [ ] 공동구매 샘플 데이터 20~30개 JSON 준비
- [ ] `POST /shopping/search` — Kiln API로 조건 추출 + **예산 기준 1인당 비용 계산 필수 포함** (`CLAUDE.md` 0번 원칙 6, 6번 참고 — 단순 목록 나열 금지)
- [ ] (프론트 연결) 공동구매 홈·상품비교 화면 → 위 API 연동, 선택 시 정산방 자동 생성 연결

## Phase 6 — README & 발표 준비 (44~48h)

- [ ] README.md 작성 — `CLAUDE.md` 1번의 선언 문장 그대로 사용
- [ ] Declared Function 위계(정산=메인, 쇼핑/분쟁=보조) 명확히 서술
- [ ] Kiln API 단계별 토큰 사용량 표 + 에너지 절감 설명 작성
- [ ] Run 1 / Run 2 로그·TxHash 캡처 첨부
- [ ] 발표 리허설

## 절대 순서를 어기지 말 것

> Phase 1(정산 코어+블록체인)이 안 끝났는데 Phase 5(Shopping 모듈)로 넘어가지 않는다. Shopping은 코어의 "선택적 확장"일 뿐, 코어보다 먼저 손대지 않는다. 시간이 부족하면 Phase 4~5는 통째로 스킵해도 되지만, Phase 1~2(정산 코어+Dispute)는 반드시 완성해야 심사 기준을 충족한다.
