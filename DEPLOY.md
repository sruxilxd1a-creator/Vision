# 웹 배포 가이드 — 외부에서 접근 가능하게 올리기

## 왜 GitHub Pages만으로는 안 되나

이 프로젝트는 두 부분이다.

- `index.html` — 정적 파일. 브라우저에서 그냥 열린다.
- `server.py` — 파이썬 서버. **실행**되어야 한다. Gemini 호출·API 키를 담당.

GitHub Pages는 정적 파일만 호스팅한다. 여기에 올리면 `index.html`은 뜨지만
`server.py`는 실행되지 않아 `/api/classify` 호출이 전부 실패한다. 카메라는
켜지는데 계속 "탐색 중"에만 머무는 증상이 바로 이것이다.

해결책: **프론트와 백엔드를 각자 맞는 곳에 따로 배포**한다.

```
[ index.html ]  →  GitHub Pages / Netlify  (정적 호스팅)
       │ fetch
       ▼
[ server.py  ]  →  Render / Railway        (파이썬 실행 + HTTPS)
       │
       ▼
   Gemini API
```

---

## ⚠️ 먼저 — API 키를 깃에 올리지 말 것

- `.env`(실제 키가 든 파일)는 **절대 커밋 금지**. 동봉된 `.gitignore`가 막아준다.
- 커밋·푸시할 파일은 `.env.example`(빈 템플릿)뿐이다.
- 이미 실제 키를 푸시했다면: AI Studio에서 그 키를 **삭제하고 새로 발급**한다.
  공개 저장소의 키는 봇이 수 분 내에 긁어간다.
- 실제 키는 백엔드 호스팅의 **환경변수 설정 화면**에만 입력한다(코드 아님).

---

## 1단계 — 백엔드 배포 (Render 예시)

Render와 Railway 둘 다 비슷하다. 여기서는 Render 기준.

1. 이 프로젝트(`proj/` 폴더 내용)를 GitHub 저장소에 푸시.
   `.env`는 빠지고 `.env.example`만 올라가는 게 정상.

2. https://render.com 가입 → New → Web Service → 해당 GitHub 저장소 선택.

3. 설정값:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn server:app --bind 0.0.0.0:$PORT --timeout 60`
     (동봉된 `Procfile`이 있어 자동 인식되기도 한다)

4. Environment(환경변수) 탭에서 키 추가:
   - `GEMINI_API_KEY` = 본인의 실제 키

5. Deploy. 끝나면 `https://your-app.onrender.com` 같은 주소가 나온다.

6. 확인: 브라우저에서 `https://your-app.onrender.com/api/health` 접속.
   `{"ok": true, ...}` 가 보이면 백엔드 정상.

> 무료 등급 주의: 일정 시간 트래픽이 없으면 서버가 잠든다(cold start).
> 잠든 뒤 첫 요청은 응답까지 수십 초 걸릴 수 있다.

---

## 2단계 — 프론트엔드의 API_BASE 설정

`index.html` 상단(스크립트 시작부)에 이 줄이 있다:

```js
var API_BASE = "";
```

1단계에서 받은 백엔드 주소를 여기에 넣는다:

```js
var API_BASE = "https://your-app.onrender.com";
```

이렇게 하면 어디에 호스팅된 `index.html`이든 그 백엔드를 호출한다.

---

## 3단계 — 프론트엔드 배포

`index.html`은 정적이라 어디든 올릴 수 있다.

- **가장 간단**: 백엔드(Render)가 이미 `index.html`을 같이 서빙한다.
  `https://your-app.onrender.com` 에 그냥 접속하면 프론트까지 다 뜬다.
  이 경우 `API_BASE`는 `""`(빈 문자열)로 둬도 된다 — 같은 주소니까.
  → **별도 프론트 배포가 필요 없다. 가장 권장.**

- 굳이 분리하고 싶다면: `index.html`을 GitHub Pages나 Netlify에 올리고,
  위 2단계대로 `API_BASE`에 백엔드 주소를 박는다.

대부분의 경우 첫 번째 방법이 맞다. 백엔드 하나만 배포하면 프론트·API가
한 주소에서 다 돈다.

---

## 흔한 막힘 점검표

| 증상 | 원인 / 해결 |
|------|------------|
| 계속 "탐색 중", 태스크 안 잡힘 | 백엔드 미배포 또는 `API_BASE` 오설정. `/api/health` 먼저 확인 |
| 카메라가 안 켜짐 | HTTPS가 아니어서. 배포 주소는 https라 정상. 로컬은 localhost만 허용 |
| `/api/health`는 되는데 분류 실패 | 환경변수 `GEMINI_API_KEY` 누락. 호스팅 설정에서 확인 |
| 첫 요청이 매우 느림 | 무료 등급 cold start. 정상. 잠시 기다리면 됨 |
| 한참 쓰다 분류가 멈춤 | Gemini 무료 한도(분당/일일) 초과. 프론트가 자동으로 간격을 늘림 |
| 음성 인식이 안 됨 | iOS 사파리 미지원. 안드로이드 크롬 권장. 버튼으로는 진행 가능 |

---

## 로컬에서 먼저 테스트하려면

배포 전에 본인 PC에서 확인하는 게 빠르다.

```
cp .env.example .env      # .env 에 실제 키 입력
pip install -r requirements.txt
python server.py
```

→ http://localhost:8000 접속. 폰 테스트는 README.md의 HTTPS 항목 참고.
