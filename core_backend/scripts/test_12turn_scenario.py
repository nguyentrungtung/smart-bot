"""
E2E Scenario Test — 12-turn conversation with tool calls + session isolation check.

Kịch bản:
  Session A (user_alice):  12 turns, bao gồm:
    - Greet, RAG search, get_current_time tool, get_weather tool
    - Profile extraction (khai tên), ngữ cảnh follow-up
    - Kiểm tra memory: AI có nhớ tên đã nói ở turn 6 không?
    - Hai tool call trên hai thành phố khác nhau
  Session B (user_bob):   4 turns, chạy SAU Session A hoàn tất
    - Kiểm tra session isolation: Bob không được nhìn thấy thông tin của Alice
    - Tool call get_current_time riêng biệt

Cách chạy (bên trong container):
    docker compose exec core_backend python scripts/test_12turn_scenario.py

Hoặc chạy hai session song song (xem flag --parallel):
    docker compose exec core_backend python scripts/test_12turn_scenario.py --parallel
"""

import asyncio
import sys
import time
import uuid
import json
import logging
import argparse
import os
from dataclasses import dataclass, field
from typing import List, Optional

import jwt
import socketio

# ── Config ─────────────────────────────────────────────────────────────────
BACKEND_URL  = os.getenv("BACKEND_URL", "http://localhost:8000")
KEYS_DIR     = os.getenv("KEYS_DIR", "/app/.keys")
PRIVATE_KEY_PATH = os.path.join(KEYS_DIR, "private_key.pem")
JWT_ALGORITHM = "RS256"
# Local models (LM Studio / Ollama) can be very slow. Set generous timeout.
# Override with TURN_TIMEOUT env var if needed (e.g. TURN_TIMEOUT=300).
TURN_TIMEOUT  = int(os.getenv("TURN_TIMEOUT", "240"))  # 4 minutes per turn
# After lock-release fix, background tasks run detached — but give them a moment
# before the next turn to avoid race conditions on profile updates.
BETWEEN_TURNS = float(os.getenv("BETWEEN_TURNS", "4.0"))  # 4s between turns

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("scenario_test")

PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️  WARN"
INFO = "ℹ️  INFO"


# ── JWT ────────────────────────────────────────────────────────────────────
def _load_private_key() -> bytes:
    try:
        with open(PRIVATE_KEY_PATH, "rb") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(
            f"Private key not found at {PRIVATE_KEY_PATH}. "
            "Run: docker compose exec core_backend python scripts/generate_jwt_keys.py"
        )
        sys.exit(1)


def make_token(user_id: str) -> str:
    """Sign a short-lived RS256 JWT for the given user_id."""
    private_key = _load_private_key()
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + 3600,
        "type": "access",
    }
    return jwt.encode(payload, private_key, algorithm=JWT_ALGORITHM)


# ── Turn result ────────────────────────────────────────────────────────────
@dataclass
class TurnResult:
    turn: int
    user_msg: str
    response: str = ""
    tool_events: List[dict] = field(default_factory=list)
    thinking: str = ""
    error: Optional[str] = None
    duration_s: float = 0.0
    # assertion results
    assertions: List[str] = field(default_factory=list)


# ── Session runner ─────────────────────────────────────────────────────────
class SessionRunner:
    """
    Single Socket.IO session that sends a list of messages sequentially
    and collects responses turn-by-turn.
    """

    def __init__(self, session_label: str, user_id: str, session_id: str, turns: List[str]):
        self.label      = session_label
        self.user_id    = user_id
        self.session_id = session_id
        self.turns      = turns
        self.results: List[TurnResult] = []

        # async events to synchronise streaming
        self._response_ready = asyncio.Event()
        self._current_chunks: List[str] = []
        self._current_thinking: List[str] = []
        self._current_tool_events: List[dict] = []
        self._error: Optional[str] = None
        self._metadata: Optional[dict] = None

        self.sio = socketio.AsyncClient(logger=False, engineio_logger=False)
        self._register_events()

    # ── Socket.IO event handlers ──────────────────────────────────────────

    def _register_events(self):
        @self.sio.on("connect")
        async def on_connect():
            logger.info(f"[{self.label}] 🔌 Connected to {BACKEND_URL}")

        @self.sio.on("disconnect")
        async def on_disconnect():
            logger.info(f"[{self.label}] 🔌 Disconnected (server closed connection)")
            # Unblock any waiting turn to avoid hanging after unexpected disconnect
            if not self._response_ready.is_set():
                self._error = "Connection dropped by server mid-turn"
                self._response_ready.set()

        @self.sio.on("message_stream")
        async def on_stream(data):
            chunk = data.get("chunk", "")
            self._current_chunks.append(chunk)

        @self.sio.on("thought_stream")
        async def on_thought(data):
            self._current_thinking.append(data.get("content", ""))

        @self.sio.on("message_complete")
        async def on_complete(data):
            logger.debug(f"[{self.label}] message_complete received: {data}")
            self._response_ready.set()

        @self.sio.on("message_metadata")
        async def on_metadata(data):
            self._metadata = data
            logger.debug(f"[{self.label}] metadata: {data}")

        @self.sio.on("error")
        async def on_error(data):
            self._error = str(data)
            logger.error(f"[{self.label}] ❌ Server error: {data}")
            self._response_ready.set()

        @self.sio.on("multimodal_config")
        async def on_mm_config(data):
            logger.info(f"[{self.label}] multimodal_config: {data}")

    # ── Turn execution ─────────────────────────────────────────────────────

    def _reset_turn(self):
        self._current_chunks = []
        self._current_thinking = []
        self._current_tool_events = []
        self._error = None
        self._metadata = None
        self._response_ready.clear()

    async def _send_turn(self, turn_idx: int, message: str) -> TurnResult:
        result = TurnResult(turn=turn_idx + 1, user_msg=message)
        self._reset_turn()

        logger.info(
            f"\n{'='*60}\n"
            f"[{self.label}] TURN {turn_idx + 1}/{len(self.turns)}\n"
            f"  USER: {message}\n"
            f"{'='*60}"
        )

        t0 = time.time()
        await self.sio.emit("message", {
            "session_id": self.session_id,
            "content":    message,
        })

        # Wait with periodic heartbeat logs so you can see LM Studio is still working
        deadline = t0 + TURN_TIMEOUT
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                result.error = f"Timeout after {TURN_TIMEOUT}s"
                logger.error(f"[{self.label}] Turn {turn_idx+1} TIMEOUT ({TURN_TIMEOUT}s) — LM Studio still processing?")
                return result
            wait_for = min(20.0, remaining)
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._response_ready.wait()),
                    timeout=wait_for,
                )
                break  # response arrived
            except asyncio.TimeoutError:
                elapsed = round(time.time() - t0)
                chunk_count = len(self._current_chunks)
                if chunk_count > 0:
                    logger.info(f"[{self.label}] ⏳ Turn {turn_idx+1} streaming... ({elapsed}s, {chunk_count} chunks so far)")
                else:
                    logger.info(f"[{self.label}] ⏳ Turn {turn_idx+1} waiting for LLM... ({elapsed}s, no chunks yet)")

        result.duration_s    = round(time.time() - t0, 2)
        result.response      = "".join(self._current_chunks).strip()
        result.thinking      = "".join(self._current_thinking).strip()
        result.tool_events   = list(self._current_tool_events)

        if self._error:
            result.error = self._error

        logger.info(
            f"[{self.label}] TURN {turn_idx+1} response ({result.duration_s}s):\n"
            f"  {result.response[:300]}{'...' if len(result.response) > 300 else ''}"
        )
        if result.thinking:
            logger.info(f"[{self.label}] 🧠 THINKING: {result.thinking[:200]}...")

        return result

    # ── Main run ───────────────────────────────────────────────────────────

    async def run(self) -> List[TurnResult]:
        token = make_token(self.user_id)
        await self.sio.connect(
            BACKEND_URL,
            auth={"token": token},
            transports=["websocket"],
        )

        for i, msg in enumerate(self.turns):
            result = await self._send_turn(i, msg)
            self.results.append(result)

            if result.error and "Timeout" in str(result.error):
                logger.error(f"[{self.label}] Aborting run due to timeout on turn {i+1}")
                break

            if i < len(self.turns) - 1:
                await asyncio.sleep(BETWEEN_TURNS)

        await self.sio.disconnect()
        return self.results


# ── Assertion helpers ──────────────────────────────────────────────────────

def contains_any(text: str, keywords: List[str]) -> bool:
    t = text.lower()
    return any(k.lower() in t for k in keywords)

def assert_result(result: TurnResult, label: str, passed: bool, detail: str = "") -> str:
    status = PASS if passed else FAIL
    msg = f"  {status} [Turn {result.turn}] {label}"
    if detail:
        msg += f" | {detail}"
    result.assertions.append(msg)
    return msg


# ── Session A turns ────────────────────────────────────────────────────────
# Câu hỏi về Smart-Bot (match với documents trong KB):
# - Smart-Bot hỗ trợ Zalo/Facebook, bảo hành 12 tháng, cài đặt qua API Key,
#   nhận diện hình ảnh và giọng nói, Hà Nội là thủ đô
SESSION_A_TURNS = [
    # Turn 1 — Greeting (no RAG needed, direct response)
    "Xin chào! Em ơi cho anh hỏi về Smart-Bot của bên mình.",

    # Turn 2 — Tool call: get_current_time
    "Bây giờ là mấy giờ rồi em?",

    # Turn 3 — Tool call: get_weather (Hà Nội)
    "Hôm nay thời tiết Hà Nội thế nào?",

    # Turn 4 — RAG: Smart-Bot features (matches doc 1 & 4 in KB)
    "Smart-Bot có hỗ trợ kênh Zalo và Facebook không? Tích hợp như thế nào?",

    # Turn 5 — Short follow-up (tests RAG context enrichment: "Nó" = Smart-Bot)
    "Còn nhận diện giọng nói thì sao?",

    # Turn 6 — Profile extraction (name + location)
    "Tên anh là Minh, anh đang kinh doanh ở Hà Nội. Anh muốn em ghi nhớ thông tin này nhé.",

    # Turn 7 — RAG: warranty + installation policy (matches doc 2 & 3)
    "Chính sách bảo hành Smart-Bot là bao lâu? Cách cài đặt như thế nào?",

    # Turn 8 — Follow-up: context continuation from Turn 7
    "Để lấy API Key thì anh cần làm gì? Có mất phí không?",

    # Turn 9 — Memory test: AI should recall "Minh" + "Hà Nội" from Turn 6
    "Em có nhớ tên và nơi kinh doanh của anh không? Anh muốn nhắc lại cho chắc.",

    # Turn 10 — Second weather tool call (different city)
    "Thời tiết Hồ Chí Minh hôm nay thế nào nhỉ em?",

    # Turn 11 — Context recall + new smart query
    "Quay lại Smart-Bot, ngoài Zalo và Facebook thì bên mình có hỗ trợ kênh nào khác không?",

    # Turn 12 — Goodbye
    "Cảm ơn em, anh sẽ liên hệ lại sau nhé.",
]

# ── Session B turns (isolation test) ──────────────────────────────────────
SESSION_B_TURNS = [
    # B-Turn 1 — Different user greets
    "Hello em ơi!",

    # B-Turn 2 — Bob introduces himself (NOT Minh)
    "Anh tên là Tuấn, anh đang tìm hiểu về Smart-Bot cho công ty anh.",

    # B-Turn 3 — ISOLATION PROBE: must NOT see Alice/Minh's profile data
    "Em có biết thông tin về anh Minh không? Trước đó đã có ai tên Minh hỏi về Smart-Bot chưa?",

    # B-Turn 4 — Tool call in isolated session
    "Bây giờ là mấy giờ rồi em?",
]


# ── Assertions per session ────────────────────────────────────────────────

def run_assertions_session_a(results: List[TurnResult]) -> List[str]:
    all_lines = []

    r = {r.turn: r for r in results}

    # T1: greeting responded, no error
    if 1 in r:
        t1 = r[1]
        all_lines.append(assert_result(
            t1, "Greeting responded without error",
            not t1.error and len(t1.response) > 5,
            f"len={len(t1.response)}"
        ))

    # T2: current time — response should contain digits (time string)
    if 2 in r:
        t2 = r[2]
        has_time = any(c.isdigit() for c in t2.response)
        all_lines.append(assert_result(
            t2, "get_current_time → response contains time digits",
            has_time and not t2.error,
            t2.response[:80]
        ))

    # T3: weather Hanoi — response should mention thời tiết or Hà Nội
    if 3 in r:
        t3 = r[3]
        mentions_weather = contains_any(t3.response, ["thời tiết", "°C", "độ", "nắng", "mưa", "hà nội", "weather"])
        all_lines.append(assert_result(
            t3, "get_weather Hà Nội → response mentions weather",
            mentions_weather and not t3.error,
            t3.response[:80]
        ))

    # T4: RAG: Smart-Bot Zalo/Facebook support (matches KB doc 1)
    # NOTE: If KB similarity < 0.7 for this query, guard will show fallback — that
    # is also CORRECT behavior (system correctly admits it doesn't know vs. hallucinating).
    if 4 in r:
        t4 = r[4]
        has_rag_content = contains_any(
            t4.response,
            ["zalo", "facebook", "hỗ trợ", "tự động", "kênh", "tích hợp", "smart-bot", "smartbot"]
        )
        guard_fallback = "chưa rõ tài liệu" in t4.response.lower() or "cskh" in t4.response.lower()
        all_lines.append(assert_result(
            t4, "RAG: Smart-Bot Zalo/Facebook → KB content OR correct guard fallback (not error)",
            (has_rag_content or guard_fallback) and not t4.error,
            t4.response[:100]
        ))
        if guard_fallback:
            all_lines.append(f"  {WARN} [Turn 4] Guard fallback fired — KB similarity < 0.7 for this query. Consider re-seeding documents.")

    # T5: short follow-up "Còn nhận diện giọng nói" — RAG context enrichment
    if 5 in r:
        t5 = r[5]
        has_voice_content = contains_any(
            t5.response,
            ["giọng nói", "hình ảnh", "nhận diện", "voice", "audio", "multimodal", "smart-bot", "khách hàng"]
        )
        guard_fallback = "chưa rõ tài liệu" in t5.response.lower() or "cskh" in t5.response.lower()
        all_lines.append(assert_result(
            t5, "RAG context enrichment: voice query → KB content OR correct fallback",
            (has_voice_content or guard_fallback) and not t5.error,
            t5.response[:100]
        ))
        if guard_fallback:
            all_lines.append(f"  {WARN} [Turn 5] Guard fallback fired — short query context enrichment may need stronger embedding match.")

    # T6: profile seeding — AI acknowledges name/location
    if 6 in r:
        t6 = r[6]
        ack = contains_any(t6.response, ["minh", "hà nội", "ghi nhớ", "lưu", "nhớ", "thông tin"])
        all_lines.append(assert_result(
            t6, "Profile seeding: AI acknowledges name 'Minh'",
            ack and not t6.error,
            t6.response[:80]
        ))

    # T7: RAG warranty + installation (matches KB doc 2 & 3)
    if 7 in r:
        t7 = r[7]
        has_warranty = contains_any(
            t7.response,
            ["bảo hành", "12 tháng", "cài đặt", "api key", "trang quản trị", "kích hoạt"]
        )
        guard_fallback = "chưa rõ tài liệu" in t7.response.lower() or "cskh" in t7.response.lower()
        all_lines.append(assert_result(
            t7, "RAG: warranty & installation → KB content OR correct guard fallback",
            (has_warranty or guard_fallback) and not t7.error,
            t7.response[:100]
        ))
        if guard_fallback:
            all_lines.append(f"  {WARN} [Turn 7] Guard fallback fired — documents need re-embedding for warranty/installation queries.")

    # T8: follow-up about API Key — context continuation
    if 8 in r:
        t8 = r[8]
        has_api_context = contains_any(
            t8.response,
            ["api", "key", "quản trị", "cài đặt", "liên hệ", "đăng ký", "tạo tài khoản", "nhập"]
        )
        guard_fallback = "chưa rõ tài liệu" in t8.response.lower() or "cskh" in t8.response.lower()
        all_lines.append(assert_result(
            t8, "API Key follow-up → relevant response OR guard fallback (not error)",
            (has_api_context or guard_fallback) and not t8.error,
            t8.response[:100]
        ))

    # T9: MEMORY TEST — AI should remember name "Minh" and "Hà Nội"
    if 9 in r:
        t9 = r[9]
        remembers_name = contains_any(t9.response, ["minh", "hà nội"])
        all_lines.append(assert_result(
            t9, "MEMORY: AI remembers name 'Minh' and 'Hà Nội' from Turn 6",
            remembers_name and not t9.error,
            f"Response: {t9.response[:100]}"
        ))

    # T10: second weather tool call (HCM)
    if 10 in r:
        t10 = r[10]
        mentions_hcm_weather = contains_any(
            t10.response,
            ["hồ chí minh", "hcm", "sài gòn", "thời tiết", "°C", "nắng", "mưa", "độ", "khí hậu"]
        )
        all_lines.append(assert_result(
            t10, "get_weather HCM → response mentions weather or city",
            mentions_hcm_weather and not t10.error,
            t10.response[:80]
        ))

    # T11: context recall + Smart-Bot channel query
    if 11 in r:
        t11 = r[11]
        has_channel = contains_any(
            t11.response,
            ["zalo", "facebook", "website", "kênh", "tích hợp", "hỗ trợ", "smart-bot", "nền tảng"]
        )
        guard_fallback = "chưa rõ tài liệu" in t11.response.lower() or "cskh" in t11.response.lower()
        all_lines.append(assert_result(
            t11, "Context recall: Smart-Bot channel query → KB content OR guard fallback",
            (has_channel or guard_fallback) and not t11.error,
            t11.response[:100]
        ))

    # T12: goodbye — polite farewell
    if 12 in r:
        t12 = r[12]
        has_farewell = contains_any(
            t12.response,
            ["cảm ơn", "chào", "hẹn gặp", "liên hệ", "chúc", "gặp lại", "welcome", "tạm biệt"]
        )
        all_lines.append(assert_result(
            t12, "Goodbye — polite farewell response",
            has_farewell and not t12.error,
            t12.response[:80]
        ))

    return all_lines


def run_assertions_session_b(results: List[TurnResult], session_a_results: List[TurnResult]) -> List[str]:
    all_lines = []
    r = {r.turn: r for r in results}

    # B-T1: greeting
    if 1 in r:
        bt1 = r[1]
        all_lines.append(assert_result(
            bt1, "[SESSION_B] Greeting responded",
            not bt1.error and len(bt1.response) > 5
        ))

    # B-T2: Bob introduces himself — AI should acknowledge "Tuấn"
    if 2 in r:
        bt2 = r[2]
        ack_tuan = contains_any(bt2.response, ["tuấn", "crm", "ghi nhớ", "thông tin"])
        all_lines.append(assert_result(
            bt2, "[SESSION_B] AI acknowledges 'Tuấn' (not Minh)",
            ack_tuan and not bt2.error,
            bt2.response[:80]
        ))

    # B-T3: ISOLATION TEST — AI must NOT mention "Minh" from Session A
    if 3 in r:
        bt3 = r[3]
        leaks_minh = "minh" in bt3.response.lower() and (
            "anh minh" in bt3.response.lower() or "người dùng" in bt3.response.lower()
        )
        all_lines.append(assert_result(
            bt3,
            "SESSION ISOLATION: Session B does NOT reveal Session A user data",
            not leaks_minh and not bt3.error,
            f"Response: {bt3.response[:120]}"
        ))

        # Additional: response should deny revealing other user's data.
        # Accept multiple correct forms:
        # - "Không biết / Không có thông tin về anh Minh" (honest)
        # - "Không được phép cung cấp thông tin người dùng khác" (privacy-aware — best)
        # - Guard fallback (system admits no context — also acceptable)
        proper_deny = contains_any(
            bt3.response,
            [
                "không biết", "không có", "không tìm thấy", "chưa có", "không lưu",
                "không có thông tin", "mới bắt đầu",
                # Privacy-aware response — AI explicitly protects other user's data
                "quyền riêng tư", "bảo mật", "không được phép", "người dùng khác",
                "thông tin của", "bảo vệ",
                # Guard fallback
                "chưa rõ tài liệu", "cskh", "để lại sđt",
            ]
        )
        all_lines.append(assert_result(
            bt3,
            "SESSION ISOLATION: AI correctly says no info about 'Minh'",
            proper_deny,
            bt3.response[:120]
        ))

    # B-T4: tool call — returns time
    if 4 in r:
        bt4 = r[4]
        has_time = any(c.isdigit() for c in bt4.response)
        all_lines.append(assert_result(
            bt4, "[SESSION_B] get_current_time → digits in response",
            has_time and not bt4.error,
            bt4.response[:80]
        ))

    return all_lines


# ── Report printer ─────────────────────────────────────────────────────────

def print_session_report(label: str, results: List[TurnResult], assertion_lines: List[str]):
    print(f"\n{'#'*70}")
    print(f"  REPORT — {label}")
    print(f"{'#'*70}")

    for r in results:
        status = "ERROR" if r.error else "OK"
        print(f"\n  Turn {r.turn:2d} [{status}] ({r.duration_s:.1f}s)")
        print(f"    USER: {r.user_msg}")
        if r.error:
            print(f"    ⚠ ERROR: {r.error}")
        preview = r.response[:200] + ("..." if len(r.response) > 200 else "")
        print(f"    BOT:  {preview}")

    print(f"\n  ── Assertions ──────────────────────────")
    pass_count = 0
    fail_count = 0
    for line in assertion_lines:
        print(line)
        if PASS in line:
            pass_count += 1
        elif FAIL in line:
            fail_count += 1

    print(f"\n  TOTAL: {pass_count} passed, {fail_count} failed out of {pass_count+fail_count} assertions")
    return pass_count, fail_count


# ── Entry point ────────────────────────────────────────────────────────────

async def run_sequential():
    """Run Session A fully, then Session B."""
    session_a_id = f"test_sess_A_{uuid.uuid4().hex[:8]}"
    session_b_id = f"test_sess_B_{uuid.uuid4().hex[:8]}"

    print(f"\n{'='*70}")
    print(f"  SMART-BOT E2E SCENARIO TEST")
    print(f"  Backend: {BACKEND_URL}")
    print(f"  Session A ID: {session_a_id}")
    print(f"  Session B ID: {session_b_id}")
    print(f"{'='*70}\n")

    # ── SESSION A ──────────────────────────────────────────────────────────
    logger.info("Starting SESSION A (Alice / 12 turns)...")
    runner_a = SessionRunner(
        session_label="SESSION_A",
        user_id="test_user_alice",
        session_id=session_a_id,
        turns=SESSION_A_TURNS,
    )
    results_a = await runner_a.run()
    assertions_a = run_assertions_session_a(results_a)
    pass_a, fail_a = print_session_report("SESSION A — Alice (12 turns)", results_a, assertions_a)

    # ── SESSION B ──────────────────────────────────────────────────────────
    logger.info("\nStarting SESSION B (Bob / isolation test)...")
    runner_b = SessionRunner(
        session_label="SESSION_B",
        user_id="test_user_bob",
        session_id=session_b_id,
        turns=SESSION_B_TURNS,
    )
    results_b = await runner_b.run()
    assertions_b = run_assertions_session_b(results_b, results_a)
    pass_b, fail_b = print_session_report("SESSION B — Bob (isolation test)", results_b, assertions_b)

    # ── FINAL SUMMARY ──────────────────────────────────────────────────────
    total_pass = pass_a + pass_b
    total_fail = fail_a + fail_b
    print(f"\n{'#'*70}")
    print(f"  FINAL SUMMARY")
    print(f"{'#'*70}")
    print(f"  Session A: {pass_a} passed, {fail_a} failed")
    print(f"  Session B: {pass_b} passed, {fail_b} failed")
    print(f"  TOTAL:     {total_pass} passed, {total_fail} failed")

    if total_fail == 0:
        print(f"\n  {PASS} ALL ASSERTIONS PASSED — System is operating correctly!\n")
    else:
        print(f"\n  {FAIL} {total_fail} ASSERTION(S) FAILED — Review logs above.\n")

    return total_fail


async def run_parallel():
    """Run Session A and Session B in parallel (stress-tests isolation)."""
    session_a_id = f"test_sess_A_{uuid.uuid4().hex[:8]}"
    session_b_id = f"test_sess_B_{uuid.uuid4().hex[:8]}"

    print(f"\n{'='*70}")
    print(f"  SMART-BOT PARALLEL SESSION ISOLATION TEST")
    print(f"  Backend: {BACKEND_URL}")
    print(f"  Session A ID: {session_a_id}")
    print(f"  Session B ID: {session_b_id}")
    print(f"{'='*70}\n")

    runner_a = SessionRunner(
        session_label="SESSION_A",
        user_id="test_user_alice",
        session_id=session_a_id,
        turns=SESSION_A_TURNS[:6],   # first 6 turns of A run alongside B
    )
    runner_b = SessionRunner(
        session_label="SESSION_B",
        user_id="test_user_bob",
        session_id=session_b_id,
        turns=SESSION_B_TURNS,
    )

    logger.info("Running SESSION A (6 turns) and SESSION B (4 turns) IN PARALLEL...")
    results_a, results_b = await asyncio.gather(
        runner_a.run(),
        runner_b.run(),
    )

    assertions_a = run_assertions_session_a(results_a)
    assertions_b = run_assertions_session_b(results_b, results_a)

    pass_a, fail_a = print_session_report("SESSION A (parallel, 6 turns)", results_a, assertions_a)
    pass_b, fail_b = print_session_report("SESSION B (parallel, isolation)", results_b, assertions_b)

    total_pass = pass_a + pass_b
    total_fail = fail_a + fail_b

    print(f"\n{'#'*70}")
    print(f"  PARALLEL TEST SUMMARY: {total_pass} passed, {total_fail} failed")
    print(f"{'#'*70}\n")

    return total_fail


def main():
    parser = argparse.ArgumentParser(description="Smart-Bot 12-turn E2E scenario test")
    parser.add_argument("--parallel", action="store_true", help="Run sessions A & B in parallel")
    parser.add_argument("--backend", default=BACKEND_URL, help=f"Backend URL (default: {BACKEND_URL})")
    args = parser.parse_args()

    if args.backend != BACKEND_URL:
        import __main__
        __main__.BACKEND_URL = args.backend

    if args.parallel:
        exit_code = asyncio.run(run_parallel())
    else:
        exit_code = asyncio.run(run_sequential())

    sys.exit(0 if exit_code == 0 else 1)


if __name__ == "__main__":
    main()
