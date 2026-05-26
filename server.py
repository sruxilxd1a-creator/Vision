"""
행동 데이터 마켓 — 태스크 분류 백엔드
======================================
프론트엔드(index.html)가 카메라 프레임 한 장을 base64로 보내면,
Gemini API로 "무슨 태스크인지" 분류해 JSON으로 돌려준다.

엔드포인트:
  POST /api/classify   { image: "data:image/jpeg;base64,..." }
    -> 200 { task, confidence, rate, surge }  (태스크 인식됨)
    -> 200 { task: null }                     (수익화할 태스크 없음)

실행:
  pip install flask google-genai python-dotenv
  export GEMINI_API_KEY=...        (또는 .env 파일)
  python server.py
"""

import os
import json
import base64
import time

from flask import Flask, request, jsonify, send_from_directory
from google import genai
from google.genai import types

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ----------------------------------------------------------------------
# 1. 설정
# ----------------------------------------------------------------------
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
if not API_KEY:
    raise SystemExit(
        "GEMINI_API_KEY 가 설정되지 않았습니다.\n"
        "  export GEMINI_API_KEY=your_key   또는 .env 파일에 적어주세요.\n"
        "  키 발급: https://aistudio.google.com/apikey"
    )

# 무료 등급에서 가장 한도가 여유로운 모델 (15 RPM / 1,000 RPD)
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")

client = genai.Client(api_key=API_KEY)

# ----------------------------------------------------------------------
# 2. 태스크 카탈로그
#    실제 서비스에서는 이 단가/목록을 DB의 "현재 수요"에서 동적으로 가져온다.
#    여기서는 고정값으로 둔다. surge(수요 급증)도 여기서 표시.
# ----------------------------------------------------------------------
TASK_CATALOG = {
    "cooking":     {"label": "조리 — 끓이기·재료 손질", "rate": 8000,  "surge": True},
    "dishwashing": {"label": "설거지 — 식기 정리",       "rate": 2500,  "surge": False},
    "assembly":    {"label": "가전·가구 조립",           "rate": 14000, "surge": True},
    "cleaning":    {"label": "청소 — 바닥·공간 정리",     "rate": 3500,  "surge": False},
    "repair":      {"label": "정비·수리 작업",           "rate": 35000, "surge": True},
    "laundry":     {"label": "빨래 — 세탁·개기",         "rate": 3000,  "surge": False},
}

# 분류기에 보여줄 후보 키 목록
TASK_KEYS = list(TASK_CATALOG.keys())

# ----------------------------------------------------------------------
# 3. Gemini 분류 프롬프트
#    핵심: 정해진 task_key 중 하나, 또는 "none" 만 고르게 강제한다.
#    단가/라벨은 우리 카탈로그에서 붙이므로 모델은 분류만 담당.
# ----------------------------------------------------------------------
SYSTEM_PROMPT = f"""너는 1인칭 시점(웨어러블/스마트폰 카메라) 이미지를 보고
사용자가 현재 어떤 '손으로 하는 일상 태스크'를 수행 중인지 분류하는 분석기다.

가능한 태스크 키는 다음뿐이다:
{json.dumps(TASK_KEYS, ensure_ascii=False)}

규칙:
- 이미지에 위 태스크 중 하나가 '명확하게 진행 중'일 때만 그 key를 고른다.
- 사람이 아무것도 안 하거나, 단순히 서 있거나, 태스크가 모호하면 "none".
- confidence 는 0~100 정수. 80 미만이면 "none" 으로 처리하는 게 낫다.
- 추측하지 말 것. 애매하면 "none".
"""

# Gemini structured output 스키마
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "task_key":   {"type": "string", "enum": TASK_KEYS + ["none"]},
        "confidence": {"type": "integer"},
        "reason":     {"type": "string"},
    },
    "required": ["task_key", "confidence", "reason"],
    "propertyOrdering": ["task_key", "confidence", "reason"],
}

CONFIDENCE_FLOOR = 80  # 이 미만이면 "태스크 없음" 처리


def decode_data_url(data_url: str):
    """ 'data:image/jpeg;base64,...' -> (mime, raw_bytes) """
    if "," not in data_url:
        raise ValueError("잘못된 data URL 형식")
    header, b64 = data_url.split(",", 1)
    mime = "image/jpeg"
    if ":" in header and ";" in header:
        mime = header.split(":", 1)[1].split(";", 1)[0]
    return mime, base64.b64decode(b64)


def classify_frame(image_bytes: bytes, mime: str) -> dict:
    """ 프레임 한 장을 Gemini로 분류. 카탈로그 정보를 붙여 반환. """
    resp = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime),
            "이 이미지를 분류하라.",
        ],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
            temperature=0,          # 분류는 결정적이어야 함
            max_output_tokens=200,
        ),
    )

    raw = (resp.text or "").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # structured output 을 써도 드물게 깨질 수 있어 방어
        return {"task": None, "_debug": "JSON 파싱 실패: " + raw[:120]}

    key = parsed.get("task_key", "none")
    conf = int(parsed.get("confidence", 0))

    # 태스크 없음 / 신뢰도 미달
    if key == "none" or key not in TASK_CATALOG or conf < CONFIDENCE_FLOOR:
        return {"task": None, "_debug": f"key={key} conf={conf}"}

    cat = TASK_CATALOG[key]
    return {
        "task": cat["label"],     # 프론트가 그대로 화면/음성에 쓰는 라벨
        "rate": cat["rate"],      # 시간당 적립액(원)
        "surge": cat["surge"],    # 수요 급증 배지 여부
        "conf": conf,             # 신뢰도(%)
        "task_key": key,          # 내부 식별용
    }


# ----------------------------------------------------------------------
# 4. Flask 앱
# ----------------------------------------------------------------------
app = Flask(__name__, static_folder=".", static_url_path="")


@app.after_request
def add_cors(resp):
    # 프론트가 다른 포트/기기에서 접근할 수 있도록 CORS 허용
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    return resp


@app.route("/api/classify", methods=["POST", "OPTIONS"])
def api_classify():
    if request.method == "OPTIONS":
        return ("", 204)

    body = request.get_json(silent=True) or {}
    data_url = body.get("image")
    if not data_url:
        return jsonify({"error": "image 필드가 필요합니다."}), 400

    try:
        mime, image_bytes = decode_data_url(data_url)
    except Exception as e:
        return jsonify({"error": f"이미지 디코딩 실패: {e}"}), 400

    t0 = time.time()
    try:
        result = classify_frame(image_bytes, mime)
    except Exception as e:
        msg = str(e)
        # 무료 등급 한도 초과 -> 프론트가 스캔 간격을 늘리도록 429 전달
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
            return jsonify({"error": "rate_limited", "detail": msg}), 429
        return jsonify({"error": "classify_failed", "detail": msg}), 500

    result["_ms"] = int((time.time() - t0) * 1000)
    return jsonify(result), 200


@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({"ok": True, "model": MODEL, "tasks": TASK_KEYS})


@app.route("/")
def index():
    # 같은 서버에서 프론트엔드(index.html)도 함께 서빙
    return send_from_directory(".", "index.html")


if __name__ == "__main__":
    print(f"[행동 데이터 마켓] 분류 백엔드 시작 — 모델: {MODEL}")
    print("  http://localhost:8000  에서 프론트엔드 + API 제공")
    # 폰 실기기 테스트: 같은 와이파이에서 http://<PC_IP>:8000 으로 접속
    app.run(host="0.0.0.0", port=8000, debug=True)
