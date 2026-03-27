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

# Import đầy đủ các API cần dùng
from mini.apis.api_setup import StartRunProgram
from mini.apis.api_action import PlayAction
from mini.apis.api_expression import PlayExpression
from mini.apis.api_sound import PlayAudio, ChangeRobotVolume
from mini.apis.api_behavior import StartBehavior, StopBehavior
from mini.apis.api_sence import FaceRecognise
from mini.apis import AudioStorageType

# Gemini SDK
from google import genai
from google.genai.types import GenerateContentConfig

# ══════════════════════════════════════════════════════════════════════
# CẤU HÌNH — Chỉ thay đổi ở đây
# ══════════════════════════════════════════════════════════════════════
SERIAL      = "EAA007UBT10000339"
TTS_DIR     = r"D:\alphamini\tts_cache"
MEMORY_FILE = r"D:\alphamini\memory.json"
LANGUAGE    = "vi-VN"

GEMINI_KEYS = [
    "AIzaSyAhkBxrI8UN7dHt41-yb7eUNlI8un9nKk8",
    "AIzaSyAWTnL1FLz8ab48qgABbkmX5V7s0mEI3fc",
    # Thêm nhiều key nếu cần
]

MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]

# Trạng thái xoay key/model
state = {"key_idx": 0, "model_idx": 0}

logging.basicConfig(level=logging.WARNING)
MiniSdk.set_log_level(logging.WARNING)
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)
os.makedirs(TTS_DIR, exist_ok=True)

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
    memory[ten_nguoi] = memory[ten_nguoi][-10:]
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

def lay_ky_uc(ten_nguoi: str) -> str:
    memory = doc_memory()
    if ten_nguoi not in memory:
        return ""
    return "\n".join([k["noi_dung"] for k in memory[ten_nguoi][-4:]])

# ══════════════════════════════════════════════════════════════════════
# AI — Gemini
# ══════════════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """Bạn là AlphaMini — robot nhỏ đáng yêu, thông minh, thân thiện tại Việt Nam.
Trả lời bằng tiếng Việt, ngắn gọn 1-2 câu, tự nhiên như đang nói chuyện thật.

Cuối mỗi câu trả lời, LUÔN thêm đúng 1 dòng JSON:
EMOTION:{"cam_xuc":"TEN","action":"TEN"}

cam_xuc: codemao10(vui), codemao13(tò mò), codemao19(dễ thương), emo_007(bình thường), emo_016(cười), emo_027(cool)
action: 011(gật đầu), 015(chào), 017(giơ tay), 037(lắc đầu), "" """

def _goi_gemini_sync(prompt: str) -> dict | None:
    total_attempts = len(GEMINI_KEYS) * len(MODELS) * 2

    for _ in range(total_attempts):
        current_key = GEMINI_KEYS[state["key_idx"] % len(GEMINI_KEYS)]
        current_model = MODELS[state["model_idx"] % len(MODELS)]

        try:
            client = genai.Client(api_key=current_key)
            config = GenerateContentConfig(
                temperature=0.8,
                max_output_tokens=220,
            )

            response = client.models.generate_content(
                model=current_model,
                contents=prompt,
                config=config
            )

            print(f"  ✅ Thành công với model: {current_model}")
            return {
                "candidates": [{
                    "content": {"parts": [{"text": response.text}]}
                }]
            }

        except Exception as e:
            error_msg = str(e).lower()
            if "403" in error_msg and ("leaked" in error_msg or "permission_denied" in error_msg):
                print(f"  ❌ KEY BỊ LEAKED → Chuyển key ngay!")
                state["key_idx"] += 1
            elif "429" in error_msg or "quota" in error_msg:
                print(f"  ⚠ Hết quota → chuyển key/model")
                state["key_idx"] += 1
            else:
                print(f"  ⚠ Lỗi với model {current_model}: {str(e)[:120]}")
                state["model_idx"] += 1

            if state["key_idx"] % len(GEMINI_KEYS) == 0:
                state["model_idx"] += 1
            continue

    print("  ❌ Tất cả key/model không hoạt động")
    return None


async def hoi_ai(cau_hoi: str, ten_nguoi: str) -> tuple:
    ky_uc = lay_ky_uc(ten_nguoi)
    context = f"\n[Ký ức về {ten_nguoi}]:\n{ky_uc}\n" if ky_uc else ""
    prompt = f"{SYSTEM_PROMPT}{context}\n{ten_nguoi}: {cau_hoi}"

    data = await asyncio.to_thread(_goi_gemini_sync, prompt)

    if data is None:
        return "Não bộ đang bận, đợi mình tí nhé!", {"cam_xuc": "codemao13", "action": ""}

    try:
        full_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        tra_loi = full_text.split("EMOTION:")[0].strip()
        emotion = {"cam_xuc": "emo_007", "action": "011"}

        if "EMOTION:" in full_text:
            try:
                emotion = json.loads(full_text.split("EMOTION:")[1].strip())
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
            await asyncio.sleep(max(1.8, len(text) * 0.10))
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
# XỬ LÝ LỆNH ĐẶC BIỆT (Nhảy, Biểu cảm, Di chuyển...)
# ══════════════════════════════════════════════════════════════════════
async def xu_ly_lenh_dac_biet(cau_hoi: str) -> bool:
    text = cau_hoi.lower().strip()

    # Nhảy múa
    if any(k in text for k in ["nhảy", "múa", "dance", "nhảy đi", "múa cho xem", "nhảy một bài", "nhảy múa"]):
        await set_expression("codemao10")
        await robot_noi("Được rồi! Mình nhảy cho bạn xem nè!")
        await StartRunProgram().execute()
        await asyncio.sleep(3)
        await StartBehavior(name="dance_0004en").execute()   # Little Star
        await asyncio.sleep(10)
        await StopBehavior().execute()
        await robot_noi("Nhảy xong rồi! Bạn thấy sao?")
        return True

    # Biểu cảm vui - cười
    if any(k in text for k in ["cười", "vui", "hạnh phúc", "smile", "cười đi"]):
        await set_expression("emo_016")
        await robot_noi("Hehe, mình cười tươi đây!")
        return True

    # Biểu cảm ngầu / cool
    if any(k in text for k in ["ngầu", "cool", "kính đen", "cool ngầu"]):
        await set_expression("emo_027")
        await robot_noi("Mình ngầu lắm nè!")
        return True

    # Biểu cảm dễ thương / yêu
    if any(k in text for k in ["yêu", "dễ thương", "thương bạn"]):
        await set_expression("codemao19")
        await robot_noi("Mình yêu bạn lắm luôn á!")
        return True

    # Tiến tới
    if any(k in text for k in ["tiến", "đi tới", "đi lên", "tiến lên"]):
        await robot_noi("Mình tiến lên nè!")
        await StartRunProgram().execute()
        await asyncio.sleep(2)
        await PlayAction(action_name="015").execute()   # chào đón
        return True

    # Lùi lại
    if any(k in text for k in ["lùi", "đi lui", "lùi lại"]):
        await robot_noi("Mình lùi lại đây!")
        await StartRunProgram().execute()
        await asyncio.sleep(2)
        await PlayAction(action_name="037").execute()   # lắc đầu
        return True

    # Vẫy tay / chào
    if any(k in text for k in ["vẫy tay", "chào tay", "giơ tay"]):
        await set_expression("emo_007")
        await robot_noi("Chào bạn nè!")
        await PlayAction(action_name="017").execute()
        return True

    return False


# ══════════════════════════════════════════════════════════════════════
# VÒNG LẶP CHAT — ĐÃ BỔ SUNG LỆNH ĐẶC BIỆT
# ══════════════════════════════════════════════════════════════════════
async def vong_lap_chat(ten_nguoi: str):
    print(f"\n  ✨ Sẵn sàng trò chuyện cùng {ten_nguoi}!")
    print("  Nói 'thoát' hoặc 'tạm biệt' để dừng")
    print("  Bạn có thể ra lệnh: nhảy đi, múa đi, cười, ngầu, yêu, tiến, lùi, vẫy tay...\n")

    while True:
        cau_hoi = await nghe_mic()
        if not cau_hoi:
            continue

        # Lệnh thoát
        if any(k in cau_hoi.lower() for k in ["thoát", "tạm biệt", "dừng", "bye", "kết thúc"]):
            await set_expression("codemao19")
            await robot_noi(f"Tạm biệt {ten_nguoi}! Hẹn gặp lại nhé.")
            await PlayAction(action_name="action_016").execute()
            luu_ky_uc(ten_nguoi, f"Kết thúc lúc {datetime.now().strftime('%H:%M')}")
            break

        # Xử lý lệnh đặc biệt trước
        if await xu_ly_lenh_dac_biet(cau_hoi):
            luu_ky_uc(ten_nguoi, f"Lệnh đặc biệt: {cau_hoi}")
            continue

        # Chat bình thường với AI
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

    await robot_noi(f"Chào {ten}! Mình là Alpha Mini, sẵn sàng trò chuyện và biểu diễn rồi!")
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