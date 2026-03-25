import asyncio, logging, os, hashlib, requests
import mini.mini_sdk as MiniSdk
from mini.apis.api_setup import StartRunProgram
from mini.apis.api_sound import PlayAudio, ChangeRobotVolume
from mini.apis import AudioStorageType

MiniSdk.set_log_level(logging.WARNING)
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)
SERIAL  = "EAA007UBT10000339"
TTS_DIR = r"D:\alphamini\tts_cache"

# Cache URL đã upload để không upload lại
URL_CACHE = {}

async def noi(text: str, wait: bool = True):
    from gtts import gTTS

    os.makedirs(TTS_DIR, exist_ok=True)
    filename = hashlib.md5(text.encode()).hexdigest() + ".mp3"
    filepath = os.path.join(TTS_DIR, filename)

    # Tạo file mp3 nếu chưa có
    if not os.path.exists(filepath):
        print(f"  Tạo TTS: '{text}'")
        gTTS(text=text, lang="vi", slow=False).save(filepath)

    # Upload lên tmpfiles.org nếu chưa upload
    if filename not in URL_CACHE:
        print(f"  Upload lên cloud...")
        with open(filepath, "rb") as f:
            resp = requests.post(
                "https://tmpfiles.org/api/v1/upload",
                files={"file": (filename, f, "audio/mpeg")}
            )
        data = resp.json()
        # tmpfiles trả về URL dạng https://tmpfiles.org/xxx/file.mp3
        # Cần đổi sang direct link
        raw_url = data["data"]["url"]
        direct_url = raw_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
        URL_CACHE[filename] = direct_url
        print(f"  URL: {direct_url}")

    url = URL_CACHE[filename]
    print(f"  🔊 '{text}'")
    (_, resp) = await PlayAudio(
        url=url,
        storage_type=AudioStorageType.NET_PUBLIC,
        volume=1.0
    ).execute()
    print(f"     isSuccess={resp.isSuccess}, code={resp.resultCode}")
    if resp.isSuccess and wait:
        await asyncio.sleep(max(2.0, len(text) * 0.12))

async def main():
    device = await MiniSdk.get_device_by_name(SERIAL, timeout=10)
    if not device:
        print("Không tìm thấy robot!"); return

    await MiniSdk.connect(device)
    print(f"Đã kết nối: {device.name}")

    # Bật âm lượng tối đa
    await ChangeRobotVolume(volume=1.0).execute()

    await StartRunProgram().execute()
    await asyncio.sleep(6)

    await noi("Xin chào! Tôi là Alpha Mini.")
    await noi("Hôm nay bạn có khỏe không?")
    await noi("Tôi rất vui được gặp bạn.")
    await noi("Tạm biệt! Hẹn gặp lại.")

    await MiniSdk.release()
    print("Xong!")

asyncio.run(main())