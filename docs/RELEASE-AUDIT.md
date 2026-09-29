# Share Pie 정식 버전 검수 (2026-09-30)

정식 버전 전 마지막 검수예요. 서버 API 전부와 화면의 모든 기능을 정상 경로·틀린 경로로 확인했고,
소셜 로그인·친구 초대 링크·쓰지 않는 옛 기능을 지웠어요. 결과는 모두 자동 검사로 남아 있어 다시 돌릴 수 있어요.

## 요약
| 항목 | 결과 |
|---|---|
| 서버 API | **92개(메서드별)** 전수 검사 — 서버 오류(500) **0건** · 로그인 없이 열린 곳은 공개용뿐 · 깨진 요청은 400대로 거절 |
| 기능 정밀 검사 | 새로 만든 44개 항목 통과 (가입·로그인·잠금·찾기·재설정·변경·탈퇴·프로필·개인정보·친구·알림·대화·현금 결제·정산 취소·삭제 확인) |
| 폰 4대 화면 테스트 | **180개 통과 · 실패 0** |
| 그룹 정산방 재현 (폰 3대) | 순서·중복·확인 카드·Pie 끼어들기·입력창 통과 |
| 지갑 전체 흐름 (로컬 체인) | 연결 → 가스 자동 지급 → 충전 → 정산 → 예치 → 자동 지급 13개 통과 |
| 백엔드 검사 | 19종 통과 · 계산 평가 51/51 · 예시 형식 오류·경고 0 |
| 토큰 효율 실측 (qwen3-32b) | 토큰 −40% · 호출 −37% · 에너지 −41% · 결과 동일성 11/11 |

## 1. 삭제한 기능
| 기능 | 지운 곳 | 기존 사용자 영향 |
|---|---|---|
| **소셜 로그인** (카카오·네이버·Google·Apple) | 화면(로그인 버튼 4개 · 소셜 가입 마무리 화면 · 내 정보 '소셜 계정 연결') · 서버 API 7개 · `agent/social.py` · 설정 키 9개 · 지갑 브리지 `socialStart` · 아이콘 · 테스트 2개 · 문서(API·배포·공개 베타·.env 예시) | 없음 — 베타 서버에 소셜 키가 없어 소셜로 가입한 사람이 없음. 비밀번호 없는 계정이 로그인하면 `NO_PASSWORD` "비밀번호 재설정으로 만들어 주세요" 안내 |
| **친구 초대 링크** | 친구 찾기의 '초대 링크 만들기' 버튼·링크 표시·안내 문구 · 앱 시작 때 `?invite=` 읽기 | 없음 — 친구는 Pie ID로 요청·수락. 그룹방 친구 초대(앱 안에서 고르기)는 링크가 아니라 유지 |
| AI 후불 결제 `/api/ai/pay` | API · 서버 함수 · 브리지 `payAiFee` · 남은 상태값 | 없음 — 구독 방식으로 바뀐 뒤 화면에서 쓰지 않던 기능 |
| 옛 이름 API `/api/settle/*` (4개) | API 경로 | 없음 — 화면·테스트 어디서도 쓰지 않음 (`/api/settlement/*`가 같은 기능) |

쇼핑 검색용 `NAVER_CLIENT_ID`·지도용 `KAKAO_REST_KEY`는 로그인과 다른 기능이라 남겼어요.

## 2. 이번 검수에서 고친 것
| # | 문제 | 고친 것 · 확인 |
|---|---|---|
| F1 | 로그인한 누구나 **가입자 전체 목록**(이름·Pie ID·지갑 주소)을 받을 수 있었음 | `/api/users`는 **나와 내 친구만** · 모르는 사람은 Pie ID로만 찾기 (feature_check 개인정보) |
| F2 | 비밀번호를 `!=`로 비교해 비교 시간이 달라질 수 있음 | 시간 차 없는 비교 `hmac.compare_digest` (로그인·변경·탈퇴 3곳) |
| F3 | 쓰지 않는 AI 후불 결제 API가 남아 있음 | 삭제 (위 표) |
| F4 | 아무도 안 쓰는 옛 이름 API 4개 | 삭제 (위 표) |
| F5 | **현금 결제 기록이 서버에만 있고 화면에서 쓸 수 없었음** (미구현) | 결제자 카드 **'현금으로 받은 멤버 표시'** → 안 낸 멤버 선택 → 확인 → 온체인 `markOfflinePayment` (결제자만 · feature_check · 폰 테스트) |
| F6 | 틀린 설명 주석 (`/api/shopping/home`) | 실제 경로(`/api/groupbuy/nearby`)로 |

같은 날 앞서 고친 것 (자세한 내용은 `docs/PROMPT-CHANGES-beta1.md`):
- **그룹 정산방** C1 폰마다 메시지 순서가 다름 · C2 확인 카드 두 번 누르면 승인 요청 2개 · C3 긴 링크가 화면을 밀고 여러 줄이 뭉침 · C4 위를 읽는 중 강제로 맨 아래로
- **지갑** 결제자·이미 낸 사람이 결제를 누르면 트랜잭션 전에 막고 안내 · 블록체인 거절 사유를 한국어로 · BNB 설정 잔재 제거
- **Pie** 라이브 QA L1~L7·R1~R4 · 실측 벤치 버그 3개 (총액 오독 · '모든 사람' · 조건 변경 인원)

## 3. 기능 전수표
검사 이름: `FE`=폰 4대 화면 테스트 · `GC`=그룹방 재현 · `FC`=기능 정밀 · `SW`=API 전수 · `WE`=지갑 전체 흐름 · 그 밖은 `tests/` 파일 이름.

### 계정
| 기능 | 확인한 것 | 검사 | 결과 |
|---|---|---|---|
| 회원가입 (이메일 인증번호) | 인증번호 전 가입 차단 · 틀린 번호 거부 · 5분 만료 · 재요청 대기(2번 뒤 1분)·시간당 한도 · 빈/13자 이름 · 잘못된 이메일 · 약한 비밀번호 3종 · 중복 이메일 · Pie ID 형식·중복 | FE · FC | ✓ |
| 로그인 | 틀린 비밀번호와 없는 이메일에 같은 안내 (가입 여부 노출 안 함) · 5번 실패 → 5분 잠금 (맞는 비밀번호도) · 비밀번호 없는 계정 → 재설정 안내 | FC | ✓ |
| 로그아웃 · 로그인 유지 | 로그아웃하면 그 토큰 무효 · 토큰은 해시로만 저장·만료 · 같은 기기에서 이메일 자동 채우기 (다른 기기는 안 함) | FE · FC | ✓ |
| 아이디 찾기 | 이름 → 가린 이메일 · 없는 이름 → 오류 없이 안내 | FE · FC | ✓ |
| 비밀번호 재설정 | 메일 인증번호 · 틀린 번호·약한 비밀번호 거부 · 성공하면 옛 비밀번호 거부 · 다른 기기 로그인 끊김 | FE · FC | ✓ |
| 비밀번호 변경 | 틀린 현재 비밀번호·약한 새 비밀번호 거부 · 새 비밀번호 로그인 | FE · FC | ✓ |
| 프로필 (동네·Pie ID) | 동네 2~40자 · 남의 Pie ID 거부 · 다른 기기에서 복원 | FE · FC | ✓ |
| 회원 탈퇴 | 틀린 비밀번호 거부 · 진행 중 정산이면 불가 · 탈퇴 뒤 로그인 불가 · 같은 이메일 재가입 가능 | FE · FC | ✓ |
| 비밀번호 저장 | PBKDF2-SHA256 12만 번 + 사용자별 소금값 · 시간 차 없는 비교 | 코드 검수 | ✓ |

### 친구 · 알림 · 개인정보
| 기능 | 확인한 것 | 검사 | 결과 |
|---|---|---|---|
| 친구 요청·수락·거절·취소 | Pie ID로 찾기 · 없는 ID·내 ID 거부 · 요청만으로는 친구 아님 · 알림함 수락/거절 | FE | ✓ |
| 친구 삭제 | 삭제하면 목록에서 빠짐 | FC | ✓ |
| 사용자 목록 | **나와 친구만** · 이메일·주소 숨김 | FC | ✓ (F1) |
| 알림 | 실제 이벤트만 · 읽음 처리 · 배지 | FE · FC | ✓ |
| 개인정보 처리방침 | 수집 항목·목적·위치·블록체인·AI 처리·삭제 안내 | 코드 검수 | ✓ (문구 결정 남음 — 아래 5) |

### Pie 1:1 대화 · 추천 · 여행
| 기능 | 확인한 것 | 검사 | 결과 |
|---|---|---|---|
| 나누기 (금액·인원·조건·퍼센트·조건 변경) | 계산은 코드(1원 단위·합계 검증) · 단순 나누기는 AI 없이 · 모호하면 되묻기 | calc_check 51/51 · beta_regress · efficiency_check | ✓ |
| 대화 저장·목록·삭제 | 다른 기기에서 복원 · 삭제 | FE · FC | ✓ |
| 배달·상품 추천 | 검증된 검색·조합만 카드 · 가격 지어내기 막음 · 상황 한 줄 · 목적 버튼 4개 · 만족도 | agent_check · rec_check · beta_regress | ✓ |
| 여행 가격 (숙소·항공) | 날짜를 말해야 검색 · 금액 있는 나누기는 검색 안 함 | travel_check · 라이브 QA | ✓ |
| 불법 목적 거절 · 주제 밖 | 지출 통제로 거절 · 짧게 안내 | FE · 라이브 QA | ✓ |

### 그룹 정산방 · 정산 흐름
| 기능 | 확인한 것 | 검사 | 결과 |
|---|---|---|---|
| 방 만들기·이름 변경·친구 초대·참여·거절·나가기 | 초대 알림 · 진행 중 정산이면 못 나감 · 끝난 방은 맨 아래 | FE | ✓ |
| 대화 · 읽음 · 알림 끄기 | 서버 시각 순서 · 중복 없음 · 안 읽은 수·배너 | GC · FE | ✓ (C1) |
| Pie 끼어들기·부르기 | 숫자 든 잡담에 조용 · 여러 방식으로 부르면 답 · '그거'에 카드 안 띄움 | GC · beta_regress | ✓ |
| 조건 → 확인 카드 → 분담표 승인 | 두 번 누름·두 사람 동시 → 한 번만 · 대상자 전원 승인 → 온체인 요청 · '금액이 이상해요' 거절 | GC · FE · split_approval_check | ✓ (C2) |
| 결제(예치) · 에스크로 · 자동 지급 | MetaMask 2단계 서명 · 이의제기 기간 뒤 결제자에게 지급 · 결제자·이미 낸 사람은 트랜잭션 전에 막음 | WE · FE · chain_local_check | ✓ |
| **현금 결제 표시** | 결제자만 · 안 낸 멤버 선택 → 온체인 기록 | FC · FE | ✓ (F5 새로 연결) |
| 정산 취소 | 결제자만 · 예치한 사람 자동 환불 | FC · FE | ✓ |
| 환불 요청 · 이의제기 | AI 조사 → 판정 → 환불·기각 | FE | ✓ |
| 지출 통제 | 1인 한도·총액 한도·허용 판매처·잔액 부족·불법 목적 → 온체인 중단 기록 | FE · FC · chain_local_check | ✓ |
| 인증서·영수증 | 제3자 검토용 공개 인증서 (로그인 없이 보기) · 트랜잭션 해시 | FE · SW | ✓ |
| AI 구매 대행 | 전원 인출 승인 → AI 자동 결제 · 각자 자기 몫만 인출 | FE | ✓ |
| 동네 공동구매 | 반경 안에서만 보임 · 좌표는 안 보냄 · 참여·마감·나가기 | FE | ✓ |

### 지갑 · AI 구독 · 그 밖
| 기능 | 확인한 것 | 검사 | 결과 |
|---|---|---|---|
| 지갑 연결 · 네트워크 전환 | Sepolia 이름·ETH · 추가 거절 시 안내 · 다른 계정 안내 | WE · wallet_bridge_check | ✓ |
| 가스 자동 지급 · PIE 충전 | ETH 0인 새 지갑에 자동 지급 · 60초 쿨다운 | WE · chain_local_check | ✓ |
| AI 요금제 (Free·Pro·Max 5x·Max 20x) | 5시간·주간 한도 · 올리면 바로 결제 · 내리면 다음 주기 · 해지 예약·취소 · 한도 도달 → 규칙 답 (계산·결제는 계속) | ai_sub_check · ai_limit_check · FE | ✓ |
| AI 사용량 · 토큰 보고서 | 단계별 · CSV · 심사용 보고서 (익명·공개) | FE · SW | ✓ |
| 캘린더 | 서버 날짜 · 정산 점 · 달 이동 | calendar_check · FE | ✓ |
| 위치 (동네) | GPS → 동 이름 · 자동 추적 켜고 끄기 | FE | ✓ |
| 베타 (동의·미션·평가·보고서) | 동의한 사람만 대화 저장 · 가명 처리 | beta_check · FE | ✓ |
| 보안 | 개발용 API는 모의 체인에서만·로그인·본인 몫만 · 베타 다운로드 키 · 로그인 없이 AI 호출 불가 | security_check · SW | ✓ |

## 4. 다시 돌리는 법
```
python tests/api_sweep_check.py          # API 92개 전수
python tests/feature_check.py            # 기능 정밀 (MAIL_DEV_ECHO=1)
node tests/frontend_logic.test.mjs       # 폰 4대 (백엔드 켠 뒤)
node tests/group_chat_check.mjs          # 그룹방 재현 (백엔드 켠 뒤)
python tests/wallet_e2e_check.py         # 지갑 전체 흐름 (anvil + ethers)
python tests/token_bench.py              # 토큰 효율 실측 (서버 PC · 실제 Kiln)
```

## 5. 정식 버전 전 남은 확인
| 항목 | 누가 | 내용 |
|---|---|---|
| 라이브 서버 검수 | Claude (서버 켜면) | 새 zip으로 켠 실제 서버에서 1:1·그룹방·지갑·보안을 실제 Kiln으로 |
| 폰 MetaMask 실기기 | 팀 | 폰 MetaMask 앱 브라우저에서 연결 → 가스 도착 → 충전 → 결제 서명 → 현금 결제 표시 |
| **처리방침 문구** | 팀 결정 | "(해커톤 버전)", "해커톤 시연용" 문구를 정식 버전에 맞게 바꿀지 |
| NPU 전력값 | 팀 | 에너지 추정의 `NPU_POWER_WATTS`(기본 150 W)를 Kiln NPU 사양으로 |
| 베타 모드 | 팀 결정 | 정식 공개 때 베타 배너·미션·대화 제공 동의를 유지할지 (`APP_VERSION`·`BETA_ENABLED`) |

## 부록 A. API 전수표 (92개 · 메서드별)
🔓 = 로그인 없이 열린 공개용 (가입·로그인·찾기 · 공개 설정 · 제3자 인증서 · 공개 체인 잔액 · 익명 토큰 보고 · 베타 공개 보고서). 숫자는 HTTP 상태 코드.

| 영역 | 메서드 | 경로 | 로그인 없이 | 깨진 요청 | 빈 요청 |
|---|---|---|---|---|---|
| 서버 | GET | `/api/health` 🔓 | 200 | — | 200 |
| 서버 | GET | `/api/config` 🔓 | 200 | — | 200 |
| 계정 | POST | `/api/auth/signup` 🔓 | 422 | 400 | 422 |
| 계정 | POST | `/api/auth/login` 🔓 | 422 | 400 | 422 |
| 계정 | GET | `/api/auth/remembered` 🔓 | 200 | — | 200 |
| 계정 | POST | `/api/auth/remembered/forget` 🔓 | 200 | 200 | 200 |
| 계정 | POST | `/api/auth/email-code` 🔓 | 422 | 400 | 422 |
| 계정 | GET | `/api/auth/me` | 401 | — | 200 |
| 계정 | POST | `/api/auth/logout` 🔓 | 200 | 200 | 200 |
| 계정 | POST | `/api/auth/reset-password` 🔓 | 422 | 400 | 422 |
| 계정 | POST | `/api/auth/change-password` | 422 | 400 | 422 |
| 계정 | POST | `/api/auth/find-id` 🔓 | 422 | 400 | 422 |
| 계정 | POST | `/api/auth/withdraw` | 422 | 400 | 422 |
| 계정 | GET | `/api/users` | 401 | — | 401 |
| 계정 | GET | `/api/users/check-id` 🔓 | 200 | — | 200 |
| 계정 | GET | `/api/users/by-id/{pid}` | 401 | — | 401 |
| 친구 | GET | `/api/friends` | 401 | — | 401 |
| 친구 | POST | `/api/friends/add` | 422 | 400 | 422 |
| 친구 | GET | `/api/friends/requests` | 401 | — | 401 |
| 친구 | POST | `/api/friends/request` | 422 | 400 | 422 |
| 친구 | POST | `/api/friends/accept` | 422 | 400 | 422 |
| 친구 | POST | `/api/friends/decline` | 422 | 400 | 422 |
| 친구 | POST | `/api/friends/cancel` | 422 | 400 | 422 |
| 알림 | GET | `/api/notifs` | 401 | — | 401 |
| 알림 | POST | `/api/notifs/read` | 401 | 400 | 401 |
| 정산 | POST | `/api/settlement/refund-request` | 422 | 400 | 422 |
| 친구 | POST | `/api/friends/remove` | 422 | 400 | 422 |
| 계정 | POST | `/api/auth/profile` | 401 | 400 | 401 |
| 위치 | POST | `/api/geo/locate` | 422 | 400 | 422 |
| 지갑 | POST | `/api/members/register` | 422 | 400 | 422 |
| 지갑 | GET | `/api/members` | 401 | — | 401 |
| 지갑 | POST | `/api/wallet/charge` | 422 | 400 | 422 |
| 지갑 | GET | `/api/wallet/{address}` 🔓 | 200 | — | 200 |
| 그룹 정산방 | GET | `/api/groups` | 401 | — | 401 |
| 그룹 정산방 | POST | `/api/groups/create` | 401 | 400 | 401 |
| 그룹 정산방 | POST | `/api/groups/{gid}/update` | 401 | 400 | 401 |
| 그룹 정산방 | POST | `/api/groups/{gid}/messages` | 401 | 400 | 401 |
| 그룹 정산방 | POST | `/api/groups/{gid}/read` | 401 | 401 | 401 |
| 그룹 정산방 | POST | `/api/groups/{gid}/mute` | 422 | 400 | 422 |
| 그룹 정산방 | POST | `/api/groups/{gid}/rename` | 422 | 400 | 422 |
| 그룹 정산방 | POST | `/api/groups/{gid}/invite` | 422 | 400 | 422 |
| 그룹 정산방 | POST | `/api/groups/{gid}/join` | 401 | 401 | 401 |
| 그룹 정산방 | POST | `/api/groups/{gid}/leave` | 401 | 401 | 401 |
| 그룹 정산방 | POST | `/api/groups/{gid}/messages/{mid}/resolve` | 422 | 400 | 422 |
| 그룹 정산방 | POST | `/api/groups/{gid}/split/start` | 422 | 400 | 422 |
| 그룹 정산방 | POST | `/api/groups/{gid}/split/approve` | 401 | 400 | 401 |
| 그룹 정산방 | POST | `/api/groups/{gid}/split/reject` | 401 | 400 | 401 |
| Pie 1:1 | GET | `/api/chats` | 401 | — | 401 |
| Pie 1:1 | POST | `/api/chats/save` | 422 | 400 | 422 |
| Pie 1:1 | POST | `/api/chats/{cid}/delete` | 401 | 401 | 401 |
| Pie 1:1 | POST | `/api/chat` | 422 | 400 | 422 |
| 정산 | POST | `/api/settlement/analyze` | 422 | 400 | 422 |
| 정산 | POST | `/api/settlement/calculate` | 422 | 400 | 422 |
| 정산 | POST | `/api/settlement/explain` | 422 | 400 | 422 |
| 정산 | POST | `/api/settlement/request` | 422 | 400 | 422 |
| 정산 | POST | `/api/settlement/approve` | 422 | 400 | 422 |
| 정산 | POST | `/api/settlement/offline-payment` | 422 | 400 | 422 |
| 정산 | POST | `/api/settlement/cancel` | 422 | 400 | 422 |
| 정산 | POST | `/api/settlement/{sid}/sync` | 401 | 400 | 401 |
| 정산 | GET | `/api/settlement/{sid}` 🔓 | 401 | — | 401 |
| 정산 | GET | `/api/settlements` | 401 | — | 401 |
| 캘린더 | GET | `/api/calendar` | 401 | — | 401 |
| 이의제기 | POST | `/api/dispute/raise` | 422 | 400 | 422 |
| 이의제기 | POST | `/api/dispute/investigate` | 422 | 400 | 422 |
| 이의제기 | POST | `/api/dispute/resolve` | 422 | 400 | 422 |
| 추천·쇼핑 | POST | `/api/shopping/search` | 422 | 400 | 422 |
| 동네 공동구매 | GET | `/api/groupbuy/nearby` 🔓 | 401 | — | 401 |
| 동네 공동구매 | POST | `/api/groupbuy/create` | 422 | 400 | 422 |
| 동네 공동구매 | POST | `/api/groupbuy/{gid}/join` | 401 | 400 | 401 |
| 동네 공동구매 | POST | `/api/groupbuy/{gid}/leave` | 401 | 401 | 401 |
| 동네 공동구매 | POST | `/api/groupbuy/{gid}/close` | 401 | 401 | 401 |
| AI 구독 | GET | `/api/ai/usage` | 401 | — | 401 |
| AI 구독 | GET | `/api/ai/sub` | 401 | — | 401 |
| AI 구독 | POST | `/api/ai/subscribe` | 422 | 400 | 422 |
| AI 구독 | POST | `/api/ai/sub/cancel` | 401 | 401 | 401 |
| 토큰 보고 | GET | `/api/usage` 🔓 | 200 | — | 200 |
| 토큰 보고 | GET | `/api/usage/report.md` 🔓 | 200 | — | 200 |
| 토큰 보고 | GET | `/api/usage/calls.csv` 🔓 | 200 | — | 200 |
| 베타 | GET | `/api/beta` 🔓 | 401 | — | 401 |
| 베타 | POST | `/api/beta/consent` | 422 | 400 | 422 |
| 베타 | POST | `/api/beta/feedback` | 422 | 400 | 422 |
| ④ 추천 기록 | POST | `/api/pie/feedback` | 422 | 400 | 422 |
| 베타 | GET | `/api/beta/report` 🔓 | 200 | — | 200 |
| 베타 | GET | `/api/beta/report.md` 🔓 | 200 | — | 200 |
| 베타 | GET | `/api/beta/export.jsonl` | 403 | — | 403 |
| 개발용(모의 체인만) | POST | `/api/dev/mock-lock` | 422 | 400 | 422 |
| 개발용(모의 체인만) | POST | `/api/dev/tamper` | 422 | 400 | 422 |
| 개발용(모의 체인만) | POST | `/api/dev/fast-forward` | 422 | 400 | 422 |
| 서버 | GET | `/healthz` 🔓 | 200 | — | 200 |
| 베타 | GET | `/api/beta/storage` 🔓 | 403 | — | 403 |
| 베타 | GET | `/api/beta/bundle.zip` | 403 | — | 403 |
| 베타 | GET | `/api/beta/chain` 🔓 | 403 | — | 403 |
