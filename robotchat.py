import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

import asyncio
import logging
import json
import hashlib
import requests
import speech_recognition as sr
from datetime import datetime
import mini.mini_sdk as MiniSdk
from mini.apis.api_setup import StartRunProgram
from mini.apis.api_action import PlayAction
from mini.apis.api_expression import PlayExpression
from mini.apis.api_sound import PlayAudio, ChangeRobotVolume
from mini.apis.api_sence import FaceRecognise
from mini.apis import AudioStorageType

# === Thêm SDK Gemini mới ===
from google import genai

# ══════════════════════════════════════════════════════════════════════
# CẤU HÌNH — Chỉ thay đổi ở đây
# ══════════════════════════════════════════════════════════════════════
SERIAL      = "EAA007UBT10000339"
TTS_DIR     = r"D:\alphamini\tts_cache"
MEMORY_FILE = r"D:\alphamini\memory.json"
LANGUAGE    = "vi-VN"

# Nhiều API key để tránh quota
GEMINI_KEYS = [
    "AIzaSyDxgCJEhJ15RyEHEjFH0Q5LUHZIVyZBueM",
    "AIzaSyDCZT_AL0JSWGeSOnsuT4n7kVEB26BHwfU",
    # Thêm key khác vào đây nếu có
]

# Danh sách model (ưu tiên model mới và mạnh)
MODELS = [
    "gemini-2.5-flash",          # Model tốt nhất hiện tại (khuyến nghị)
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash-8b",
]

# ══════════════════════════════════════════════════════════════════════
# SETUP
# ══════════════════════════════════════════════════════════════════════
logging.basicConfig(level=logging.WARNING)
MiniSdk.set_log_level(logging.WARNING)
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)
os.makedirs(TTS_DIR, exist_ok=True)

# Trạng thái xoay key và model
state = {"key_idx": 0, "model_idx": 0}

# ══════════════════════════════════════════════════════════════════════
# MEMORY — File JSON
# ══════════════════════════════════════════════════════════════════════
def doc_memory() -> dict:
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def luu_ky_uc(ten_nguoi: str, noi_dung: str):
    memory = doc_memory()
    if ten_nguoi not in memory:
        memory[ten_nguoi] = []
    memory[ten_nguoi].append({
        "noi_dung": noi_dung,
        "thoi_gian": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    memory[ten_nguoi] = memory[ten_nguoi][-15:]
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

def lay_ky_uc(ten_nguoi: str) -> str:
    memory = doc_memory()
    if ten_nguoi not in memory:
        return ""
    return "\n".join([k["noi_dung"] for k in memory[ten_nguoi][-8:]])

# ══════════════════════════════════════════════════════════════════════
# AI — Gemini với Google GenAI SDK + Key Rotation + Model Fallback
# ══════════════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """Bạn là AlphaMini — robot humanoid nhỏ đáng yêu, thông minh, thân thiện tại Việt Nam.
Trả lời bằng tiếng Việt, ngắn gọn 1-2 câu, tự nhiên như đang nói chuyện thật.

Cuối mỗi câu trả lời, LUÔN thêm đúng 1 dòng JSON (không dùng markdown, không xuống dòng thêm):
EMOTION:{"cam_xuc":"TEN","action":"TEN"}

cam_xuc (chọn 1 phù hợp nhất):
  codemao10=hứng khởi/vui vẻ, codemao13=thắc mắc/tò mò, codemao17=chán nản
  codemao19=yêu thích/dễ thương, emo_007=mỉm cười bình thường
  emo_008=bực bội, emo_013=tức giận, emo_016=cười tươi rạng rỡ, emo_027=cool/ngầu

action (chọn 1 hoặc để trống):
  011=gật đầu, 015=chào đón, 010=cười, 037=lắc đầu
  017=giơ tay, action_016=tạm biệt, ""=không action

Ví dụ:
Ồ hay quá! Mình chưa biết điều đó bao giờ.
EMOTION:{"cam_xuc":"codemao10","action":"017"}"""

def _goi_gemini_sync(prompt: str) -> dict | None:
    """Gọi Gemini qua SDK chính thức, tự động xoay key và model khi quota hết"""
    total_attempts = len(GEMINI_KEYS) * len(MODELS)

    for _ in range(total_attempts):
        current_key = GEMINI_KEYS[state["key_idx"] % len(GEMINI_KEYS)]
        current_model = MODELS[state["model_idx"] % len(MODELS)]

        try:
            client = genai.Client(api_key=current_key)

            response = client.models.generate_content(
                model=current_model,
                contents=prompt
            )

            # Trả về dạng dict giống format cũ để không phải sửa phần parse
            return {
                "candidates": [{
                    "content": {
                        "parts": [{"text": response.text}]
                    }
                }]
            }

        except Exception as e:
            error_msg = str(e).lower()

            # Xử lý quota hết (429 hoặc ResourceExhausted)
            if "429" in error_msg or "quota" in error_msg or "resourceexhausted" in error_msg:
                state["key_idx"] += 1
                if state["key_idx"] % len(GEMINI_KEYS) == 0:
                    state["model_idx"] += 1
                    next_model = MODELS[state["model_idx"] % len(MODELS)]
                    print(f"  ⚠ Hết quota tất cả key → chuyển model: {next_model}")
                else:
                    next_key_num = (state["key_idx"] % len(GEMINI_KEYS)) + 1
                    print(f"  ⚠ Key {current_key[:10]}... hết quota → thử key {next_key_num}")
                continue

            else:
                print(f"  ⚠ Lỗi với model {current_model}: {str(e)[:120]}")
                state["model_idx"] += 1
                continue

    print("  ❌ Tất cả key và model đều không hoạt động được.")
    return None


async def hoi_ai(cau_hoi: str, ten_nguoi: str) -> tuple:
    ky_uc = lay_ky_uc(ten_nguoi)
    context = f"\n[Ký ức về {ten_nguoi}]:\n{ky_uc}\n" if ky_uc else ""
    prompt = f"{SYSTEM_PROMPT}{context}\n{ten_nguoi}: {cau_hoi}"

    data = await asyncio.to_thread(_goi_gemini_sync, prompt)

    if data is None:
        return "Não bộ đang bận, đợi mình tí nhé.", {"cam_xuc": "codemao13", "action": ""}

    try:
        full_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        tra_loi = full_text.split("EMOTION:")[0].strip()
        emotion = {"cam_xuc": "emo_007", "action": "011"}

        if "EMOTION:" in full_text:
            try:
                emotion_str = full_text.split("EMOTION:")[1].strip()
                emotion = json.loads(emotion_str)
            except:
                pass

        return tra_loi, emotion

    except Exception as e:
        print(f"  Parse lỗi: {e}")
        return "Mình không hiểu lắm, bạn nói lại được không?", {"cam_xuc": "codemao13", "action": "037"}


# ══════════════════════════════════════════════════════════════════════
# STT — Mic PC
# ══════════════════════════════════════════════════════════════════════
async def nghe_mic() -> str:
    def _listen():
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True
        with sr.Microphone() as source:
            print("\n  🎤 Đang nghe...")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            try:
                audio = recognizer.listen(source, timeout=6, phrase_time_limit=5)
                text = recognizer.recognize_google(audio, language=LANGUAGE)
                print(f"  👤 Bạn: {text}")
                return text
            except sr.WaitTimeoutError:
                return ""
            except sr.UnknownValueError:
                print("  (Không nghe rõ, thử lại...)")
                return ""
            except Exception as e:
                print(f"  STT lỗi: {e}")
                return ""

    return await asyncio.to_thread(_listen)


# ══════════════════════════════════════════════════════════════════════
# TTS — Robot nói
# ══════════════════════════════════════════════════════════════════════
URL_CACHE = {}

async def robot_noi(text: str):
    if not text:
        return
    try:
        from gtts import gTTS
        filename = hashlib.md5(text.encode()).hexdigest() + ".mp3"
        filepath = os.path.join(TTS_DIR, filename)

        if not os.path.exists(filepath):
            await asyncio.to_thread(lambda: gTTS(text=text, lang="vi").save(filepath))

        if filename not in URL_CACHE:
            def _upload():
                with open(filepath, "rb") as f:
                    r = requests.post(
                        "https://tmpfiles.org/api/v1/upload",
                        files={"file": (filename, f, "audio/mpeg")},
                        timeout=15
                    )
                raw = r.json()["data"]["url"]
                return raw.replace("tmpfiles.org/", "tmpfiles.org/dl/")
            URL_CACHE[filename] = await asyncio.to_thread(_upload)

        url = URL_CACHE[filename]
        print(f"  🤖 Robot: {text}")

        (_, resp) = await PlayAudio(
            url=url,
            storage_type=AudioStorageType.NET_PUBLIC,
            volume=1.0
        ).execute()

        if resp.isSuccess:
            await asyncio.sleep(max(2.0, len(text) * 0.11))
        else:
            print(f"     (Audio lỗi code={resp.resultCode})")

    except Exception as e:
        print(f"  ❌ TTS lỗi: {e}")


# ══════════════════════════════════════════════════════════════════════
# BIỂU CẢM
# ══════════════════════════════════════════════════════════════════════
async def set_expression(name: str):
    for _ in range(2):
        (_, resp) = await PlayExpression(express_name=name).execute()
        if resp.isSuccess:
            return
        await asyncio.sleep(1.5)


# ══════════════════════════════════════════════════════════════════════
# VÒNG LẶP CHAT
# ══════════════════════════════════════════════════════════════════════
async def vong_lap_chat(ten_nguoi: str):
    print(f"\n  ✨ Sẵn sàng trò chuyện cùng {ten_nguoi}!")
    print("  Nói 'thoát' hoặc 'tạm biệt' để dừng\n")

    while True:
        cau_hoi = await nghe_mic()
        if not cau_hoi:
            continue

        if any(k in cau_hoi.lower() for k in ["thoát", "tạm biệt", "dừng", "bye", "kết thúc"]):
            await set_expression("codemao19")
            await robot_noi(f"Tạm biệt {ten_nguoi}! Hẹn gặp lại nhé.")
            await PlayAction(action_name="action_016").execute()
            luu_ky_uc(ten_nguoi, f"Kết thúc lúc {datetime.now().strftime('%H:%M')}")
            break

        luu_ky_uc(ten_nguoi, f"Bạn hỏi: {cau_hoi}")

        print("  💭 Đang suy nghĩ...")
        tra_loi, emotion = await hoi_ai(cau_hoi, ten_nguoi)
        luu_ky_uc(ten_nguoi, f"Robot trả lời: {tra_loi}")

        await set_expression(emotion.get("cam_xuc", "emo_007"))
        await asyncio.sleep(0.5)

        action = emotion.get("action", "")
        if action:
            await PlayAction(action_name=action).execute()
            await asyncio.sleep(1.5)

        await robot_noi(tra_loi)
        await asyncio.sleep(0.3)


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════
async def main():
    print("  📡 Đang tìm kiếm Alpha Mini...")
    device = await MiniSdk.get_device_by_name(SERIAL, timeout=10)
    if not device:
        print("  ❌ Không thấy robot. Kiểm tra WiFi!"); return

    await MiniSdk.connect(device)
    print(f"  ✅ Đã kết nối: {device.name} @ {device.address}")

    # 1. Âm lượng
    await ChangeRobotVolume(volume=1.0).execute()
    await asyncio.sleep(1)

    # 2. Nhận diện khuôn mặt
    print("  🔍 Đang nhận diện khuôn mặt...")
    (_, resp) = await FaceRecognise(timeout=5).execute()
    ten = "bạn"
    if resp.isSuccess and resp.faceInfos:
        name = resp.faceInfos[0].name
        ten = name if name != "stranger" else "bạn"
    print(f"  👤 Xin chào: {ten}")

    # 3. Biểu cảm chào
    await set_expression("emo_016")
    await asyncio.sleep(1)

    # 4. StartRunProgram
    await StartRunProgram().execute()
    await asyncio.sleep(6)

    # 5. Chào mừng
    await robot_noi(f"Chào {ten}! Mình là Alpha Mini, sẵn sàng trò chuyện rồi!")
    await PlayAction(action_name="015").execute()
    await asyncio.sleep(3)

    # 6. Vào vòng chat
    try:
        await vong_lap_chat(ten)
    except KeyboardInterrupt:
        print("\n  (Dừng bởi người dùng)")
    except Exception as e:
        print(f"  Lỗi: {e}")
    finally:
        await MiniSdk.release()
        print("  🔌 Đã ngắt kết nối.")


if __name__ == "__main__":
    asyncio.run(main())