import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

import asyncio
import logging
import json
import hashlib
import re
import requests
import speech_recognition as sr
from datetime import datetime
import mini.mini_sdk as MiniSdk

from mini.apis.api_setup import StartRunProgram
from mini.apis.api_action import PlayAction
from mini.apis.api_expression import PlayExpression
from mini.apis.api_sound import PlayAudio, ChangeRobotVolume
from mini.apis.api_behavior import StartBehavior, StopBehavior
from mini.apis.api_sence import FaceRecognise
from mini.apis import AudioStorageType

from google import genai
from google.genai.types import GenerateContentConfig


# CẤU HÌNH

SERIAL      = "EAA007UBT10000339"
TTS_DIR     = r"D:\alphamini\tts_cache"
MEMORY_FILE = r"D:\alphamini\memory.json"
LANGUAGE    = "vi-VN"

GEMINI_KEYS = [
    "YOUR_API_KEY_1",
    "YOUR_API_KEY_2",
]

MODELS = [ 
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]

state = {"key_idx": 0, "model_idx": 0}

logging.basicConfig(level=logging.WARNING)
MiniSdk.set_log_level(logging.WARNING)
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)
os.makedirs(TTS_DIR, exist_ok=True)


# MEMORY

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
    memory[ten_nguoi] = memory[ten_nguoi][-10:]
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

def lay_ky_uc(ten_nguoi: str) -> str:
    memory = doc_memory()
    if ten_nguoi not in memory:
        return ""
    return "\n".join([k["noi_dung"] for k in memory[ten_nguoi][-4:]])


# AI — Gemini (ĐÃ SỬA ĐỂ KHÔNG ĐỌC JSON)

SYSTEM_PROMPT = """Bạn là AlphaMini — robot nhỏ đáng yêu tại Việt Nam.

Quy tắc trả lời BẮT BUỘC:
- Trả lời ngắn gọn, tối đa 2 câu bằng tiếng Việt, tự nhiên.
- KHÔNG được viết bất kỳ JSON, dấu ngoặc nhọn {} hay từ "EMOTION" vào trong câu trả lời.
- Chỉ thêm đúng **1 dòng cuối cùng** là JSON.

Ví dụ đúng:
Ồ hay quá! Mình thích ý tưởng đó.
EMOTION:{"cam_xuc":"codemao10","action":"017"}

cam_xuc chỉ dùng: codemao10, codemao13, codemao19, emo_007, emo_016, emo_027
action chỉ dùng: 011, 015, 017, 037, action_016, "" """

def _goi_gemini_sync(prompt: str) -> str | None:
    for _ in range(len(GEMINI_KEYS) * len(MODELS) * 2):
        key = GEMINI_KEYS[state["key_idx"] % len(GEMINI_KEYS)]
        model = MODELS[state["model_idx"] % len(MODELS)]
        try:
            client = genai.Client(api_key=key)
            config = GenerateContentConfig(temperature=0.75, max_output_tokens=180)
            response = client.models.generate_content(model=model, contents=prompt, config=config)
            return response.text
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "quota" in err:
                state["key_idx"] += 1
                if state["key_idx"] % len(GEMINI_KEYS) == 0:
                    state["model_idx"] += 1
            else:
                state["model_idx"] += 1
            continue
    return None


def loc_tra_loi(full_text: str) -> tuple:
    emotion = {"cam_xuc": "emo_007", "action": "011"}
    tra_loi = full_text

    if "EMOTION:" in full_text:
        parts = full_text.split("EMOTION:", 1)
        tra_loi = parts[0].strip()
        json_part = parts[1].strip()

        # Lấy đúng phần JSON
        match = re.search(r'\{.*?\}', json_part, re.DOTALL)
        if match:
            try:
                emotion = json.loads(match.group())
            except:
                pass

    # Dọn sạch mọi JSON còn sót
    tra_loi = re.sub(r'EMOTION\s*:.*', '', tra_loi, flags=re.DOTALL | re.IGNORECASE)
    tra_loi = re.sub(r'\{[^}]*\}', '', tra_loi)
    tra_loi = tra_loi.strip()

    return tra_loi, emotion


async def hoi_ai(cau_hoi: str, ten_nguoi: str) -> tuple:
    ky_uc = lay_ky_uc(ten_nguoi)
    context = f"\n[Ký ức về {ten_nguoi}]:\n{ky_uc}\n" if ky_uc else ""
    prompt = f"{SYSTEM_PROMPT}{context}\n{ten_nguoi}: {cau_hoi}"

    print("  💭 Đang suy nghĩ...")
    raw = await asyncio.to_thread(_goi_gemini_sync, prompt)

    if raw is None:
        return "Mình hơi chậm, chờ chút nhé!", {"cam_xuc": "codemao13", "action": ""}

    return loc_tra_loi(raw)



# STT — Mic PC

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



# TTS

URL_CACHE = {}

async def robot_noi(text: str):
    if not text:
        return
    # Dọn sạch JSON lần cuối
    text = re.sub(r'EMOTION\s*:.*', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'\{[^}]*\}', '', text)
    text = text.strip()

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
        print(f"   Robot: {text}")

        (_, resp) = await PlayAudio(
            url=url,
            storage_type=AudioStorageType.NET_PUBLIC,
            volume=1.0
        ).execute()

        if resp.isSuccess:
            await asyncio.sleep(max(1.7, len(text) * 0.095))
        else:
            print(f"     (Audio lỗi code={resp.resultCode})")

    except Exception as e:
        print(f"  ❌ TTS lỗi: {e}")


async def set_expression(name: str):
    for _ in range(2):
        (_, resp) = await PlayExpression(express_name=name).execute()
        if resp.isSuccess:
            return
        await asyncio.sleep(1.5)



# XỬ LÝ LỆNH ĐẶC BIỆT
async def xu_ly_lenh_dac_biet(cau_hoi: str) -> bool:
    text = cau_hoi.lower().strip()

    if any(k in text for k in ["hát", "hát đi", "hát một bài", "hát cho nghe"]):
        await set_expression("codemao10")
        await robot_noi("Oke! Mình hát cho bạn nghe nè!")
        await asyncio.sleep(0.8)
        await robot_noi("Twinkle twinkle little star...")
        await asyncio.sleep(2.5)
        await set_expression("emo_016")
        await robot_noi("How I wonder what you are...")
        await asyncio.sleep(2.5)
        await robot_noi("Up above the world so high...")
        await asyncio.sleep(2.5)
        await robot_noi("Like a diamond in the sky...")
        await asyncio.sleep(2.5)
        await set_expression("codemao19")
        await robot_noi("Hát xong rồi! Bạn thích bài này không?")
        return True

    if any(k in text for k in ["nhảy", "múa", "dance", "nhảy đi"]):
        await set_expression("codemao10")
        await robot_noi("Được rồi! Mình nhảy cho bạn xem nè!")
        await StartRunProgram().execute()
        await asyncio.sleep(3)
        await StartBehavior(name="dance_0004en").execute()
        await asyncio.sleep(10)
        await StopBehavior().execute()
        await robot_noi("Nhảy xong rồi! Bạn thấy sao?")
        return True

    return False


# VÒNG LẶP CHAT
async def vong_lap_chat(ten_nguoi: str):
    print(f"\n  ✨ Sẵn sàng trò chuyện cùng {ten_nguoi}!")
    print("  Nói 'thoát' hoặc 'tạm biệt' để dừng")
    print("  Bạn có thể ra lệnh: hát đi, nhảy đi, cười, ngầu, yêu...\n")

    while True:
        cau_hoi = await nghe_mic()
        if not cau_hoi:
            continue

        if any(k in cau_hoi.lower() for k in ["thoát", "tạm biệt", "dừng", "bye", "kết thúc"]):
            await set_expression("codemao19")
            await robot_noi(f"Tạm biệt {ten_nguoi}! Hẹn gặp lại nhé.")
            await PlayAction(action_name="action_016").execute()
            break

        if await xu_ly_lenh_dac_biet(cau_hoi):
            luu_ky_uc(ten_nguoi, f"Lệnh đặc biệt: {cau_hoi}")
            continue

        luu_ky_uc(ten_nguoi, f"Bạn hỏi: {cau_hoi}")
        print("  💭 Đang suy nghĩ...")
        tra_loi, emotion = await hoi_ai(cau_hoi, ten_nguoi)
        luu_ky_uc(ten_nguoi, f"Robot trả lời: {tra_loi}")

        await set_expression(emotion.get("cam_xuc", "emo_007"))
        await asyncio.sleep(0.3)

        action = emotion.get("action", "")
        if action:
            await PlayAction(action_name=action).execute()
            await asyncio.sleep(1.0)

        await robot_noi(tra_loi)
        await asyncio.sleep(0.2)


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════
async def main():
    print("  📡 Đang tìm kiếm Alpha Mini...")
    device = await MiniSdk.get_device_by_name(SERIAL, timeout=10)
    if not device:
        print("  ❌ Không thấy robot. Kiểm tra WiFi!")
        return

    await MiniSdk.connect(device)
    print(f"  ✅ Đã kết nối: {device.name} @ {device.address}")

    await ChangeRobotVolume(volume=1.0).execute()
    await asyncio.sleep(1)

    print("  🔍 Đang nhận diện khuôn mặt...")
    (_, resp) = await FaceRecognise(timeout=5).execute()
    ten = "bạn"
    if resp.isSuccess and resp.faceInfos:
        name = resp.faceInfos[0].name
        ten = name if name != "stranger" else "bạn"
    print(f"  👤 Xin chào: {ten}")

    await set_expression("emo_016")
    await asyncio.sleep(1)

    await StartRunProgram().execute()
    await asyncio.sleep(5)

    await robot_noi(f"Chào {ten}! Mình là Alpha Mini, sẵn sàng trò chuyện rồi!")
    await PlayAction(action_name="015").execute()
    await asyncio.sleep(2)

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