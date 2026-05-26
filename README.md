# 행동 데이터 마켓 — 라이브 캡처 MVP

모바일 카메라로 들어오는 영상을 실시간으로 분류해, 수익화 가능한 태스크가
보이면 음성으로 안내하고 "좋아" 응답 시 녹화·업로드하는 프로토타입.

태스크 분류는 **Gemini API**가 실제로 수행합니다.

## 구성

```
proj/
├── index.html      프론트엔드 — 가로 카메라 + 음성 인터랙션 (단일 파일)
├── server.py       백엔드 — 프레임을 Gemini로 분류해 JSON 반환 (Flask)
├── .env.example    API 키 템플릿
└── README.md
```

데이터 흐름: `index.html` 이 5초마다 프레임 한 장을 캡처 → `POST /api/classify`
→ `server.py` 가 Gemini API 호출 → `{task, rate, surge, conf}` 또는 `{task:null}` 반환.

## 실행 방법

1. Gemini API 키 발급 — https://aistudio.google.com/apikey (무료, 카드 불필요)

2. 키 설정 — `.env.example` 을 `.env` 로 복사 후 키 붙여넣기
   ```
   cp .env.example .env
   # .env 파일을 열어 GEMINI_API_KEY 값 입력
   ```

3. 의존성 설치 후 서버 실행
   ```
   pip install flask google-genai python-dotenv
   python server.py
   ```

4. 접속
   - PC 브라우저: http://localhost:8000
   - **폰 실기기**(권장): PC와 같은 와이파이에서 `http://<PC_IP>:8000`
     - 카메라/마이크는 보안 컨텍스트가 필요. `localhost` 는 예외로 허용되지만
       `http://192.168.x.x` 는 브라우저에 따라 막힐 수 있음 → 아래 HTTPS 참고.

## 폰에서 카메라가 안 켜질 때 (HTTPS)

모바일 브라우저는 `localhost` 외의 평문 HTTP에서 카메라를 차단합니다. 두 가지 방법:

- **ngrok**: `ngrok http 8000` → 발급된 https 주소로 폰에서 접속
- **자체 서명 인증서**로 Flask를 HTTPS 실행 (`app.run(ssl_context='adhoc')`,
  `pip install pyopenssl` 필요)

## 동작하는 것 / 아직 아닌 것

| 기능 | 상태 |
|------|------|
| 가로 카메라 프리뷰 | 실제 동작 |
| 5초 간격 프레임 캡처 | 실제 동작 |
| 태스크 분류 | **실제 (Gemini API)** |
| 음성 안내(TTS) / 응답 인식(STT) | 실제 동작 (안드로이드 크롬 권장) |
| 녹화(MediaRecorder) | 실제 동작 |
| 비식별화 · 업로드 | 진행 표시만 — 실제 연동은 다음 단계 |

## 무료 등급 주의

- `gemini-2.5-flash-lite` 무료 한도: 약 15 RPM / 1,000 RPD.
  스캔 간격 5초(분당 12회)로 잡아 한도 내에 들어가며, 초과(429) 시
  프론트가 자동으로 간격을 늘립니다.
- 무료 등급은 입력이 모델 학습에 쓰일 수 있습니다. 실제 서비스 단계에서는
  유료 등급으로 올려 이 부분을 꺼야 합니다 (프라이버시가 이 제품의 핵심).

## 분류 결과를 조정하려면

`server.py` 의 `TASK_CATALOG` — 태스크 목록·단가·surge 여부를 여기서 바꿉니다.
실제 서비스에서는 이 값을 DB의 "현재 수요"에서 동적으로 가져오게 됩니다.
`SYSTEM_PROMPT` 는 Gemini가 무엇을 보고 어떻게 분류할지를 지시하는 부분입니다.

---

## 다음 단계 (Claude Code 작업 지시서)

이 프로젝트를 Claude Code에서 이어서 발전시킬 때, 아래 순서를 권장합니다.

1. **실제 영상으로 분류 정확도 확인**
   서버를 띄우고 주방·정비 등 실제 장면을 폰으로 비춰, `server.py` 의
   `_debug` 필드(응답에 포함됨)를 보며 오분류 패턴을 점검. `SYSTEM_PROMPT`
   와 `CONFIDENCE_FLOOR` 를 조정.

2. **비식별화 파이프라인 실제 연동**
   현재 진행 표시만 있는 단계를 실제로 구현. 업로드된 영상에 얼굴 검출
   후 블러 처리. (예: 얼굴 검출 라이브러리 + 영상 프레임 처리)

3. **업로드 저장소 연결**
   녹화 Blob 을 실제 스토리지에 업로드하는 `POST /api/upload` 추가.

4. **단가의 동적화**
   `TASK_CATALOG` 고정값을 DB 기반 "현재 수요·단가" 로 교체.

각 단계는 독립적이므로 1번부터 하나씩 진행하면 됩니다.
