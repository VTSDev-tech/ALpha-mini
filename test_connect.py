import asyncio
import logging
import os
import socket
import mini.mini_sdk as MiniSdk
from mini.apis.api_setup import StartRunProgram
from mini.apis.api_action import PlayAction, MoveRobot, MoveRobotDirection, StopAllAction
from mini.apis.api_behavior import StartBehavior, StopBehavior
from mini.apis.api_expression import PlayExpression, SetMouthLamp, ControlMouthLamp
from mini.apis.api_sound import PlayAudio, ChangeRobotVolume
from mini.apis.api_sence import FaceDetect, FaceRecognise, ObjectRecognise, TakePicture
from mini.apis import AudioStorageType, MouthLampColor, MouthLampMode, ObjectRecogniseType, TakePictureType

MiniSdk.set_log_level(logging.WARNING)
MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)
SERIAL = "EAA007UBT10000339"

# ═══════════════════════════════════════════════
# HELPER — Kết nối lại robot (dùng trong demo_ket_hop)
# ═══════════════════════════════════════════════
async def reconnect():
    await MiniSdk.release()
    await asyncio.sleep(2)
    device = await MiniSdk.get_device_by_name(SERIAL, timeout=10)
    if not device:
        print("  ✗ Không tìm thấy robot khi reconnect!")
        return False
    await MiniSdk.connect(device)
    await asyncio.sleep(2)
    return True

# ═══════════════════════════════════════════════
# HELPER — Biểu cảm có retry tự động
# ═══════════════════════════════════════════════
async def set_expression(name: str, label: str = "", retries: int = 3):
    for i in range(retries):
        (_, resp) = await PlayExpression(express_name=name).execute()
        if resp.isSuccess:
            if label:
                print(f"  ✓ {label} ({name})")
            return True
        elif resp.resultCode == 1001:
            await asyncio.sleep(1.5)
        else:
            if label:
                print(f"  ✗ {label} ({name}) — code {resp.resultCode}")
            return False
    if label:
        print(f"  ✗ {label} ({name}) — thất bại sau {retries} lần")
    return False

# ═══════════════════════════════════════════════
# TTS TIẾNG VIỆT — gTTS + HTTP server
# Bước 1: pip install gtts
# Bước 2: Chạy file_server.py ở terminal khác TRƯỚC
# ═══════════════════════════════════════════════
PC_IP   = None
TTS_DIR = r"D:\alphamini\tts_cache"

def get_pc_ip():
    global PC_IP
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    PC_IP = s.getsockname()[0]
    s.close()

async def noi(text: str, wait: bool = True):
    """Robot nói tiếng Việt qua gTTS"""
    try:
        from gtts import gTTS
        import hashlib

        os.makedirs(TTS_DIR, exist_ok=True)
        filename = hashlib.md5(text.encode()).hexdigest() + ".mp3"
        filepath = os.path.join(TTS_DIR, filename)

        if not os.path.exists(filepath):
            print(f"  Tạo TTS: {text[:40]}...")
            gTTS(text=text, lang="vi", slow=False).save(filepath)

        url = f"http://{PC_IP}:8000/{filename}"
        (_, resp) = await PlayAudio(
            url=url,
            storage_type=AudioStorageType.NET_PUBLIC,
            volume=1.0
        ).execute()

        if resp.isSuccess:
            print(f"  🔊 '{text}'")
            if wait:
                await asyncio.sleep(max(2.0, len(text) * 0.12))
        else:
            print(f"  ✗ TTS lỗi code={resp.resultCode}")
            if resp.resultCode == -64:
                print("     → Đăng nhập tài khoản UBTech trong app AlphaMini")

    except ImportError:
        print("  ⚠ Chưa cài gTTS: pip install gtts")


ALL_EXPRESSIONS = [

    ("emo_026",   "Trợn mắt"),
    ("emo_027",   "Kính đen / Cool"),
    ("emo_028",   "Che mặt"),
    ("emo_029",   "Tinh ranh"),
    ("emo_030",   "Lác mắt"),
    ("emo_031",   "Kính đọc sách"),
    ("emo_032",   "Kính vàng"),
]

# ═══════════════════════════════════════════════
# 1. BIỂU CẢM MẮT — KHÔNG cần StartRunProgram
# ═══════════════════════════════════════════════
async def demo_expression():
    print
    ("=== BIEU CAM MAT (52 bieu cam) ===")
    BATCH_SIZE = 10
    for i, (name, label) in enumerate(ALL_EXPRESSIONS):
        ok = await set_expression(name, label)
        if ok:
            await asyncio.sleep(2.5)
        else:
            print(f"     -> Nghi 5 giay roi thu lai...")
            await asyncio.sleep(5)
            ok2 = await set_expression(name, label)
            await asyncio.sleep(2.5 if ok2 else 1)
        if (i + 1) % BATCH_SIZE == 0 and (i + 1) < len(ALL_EXPRESSIONS):
            print(f"  -- Nghi 8 giay de robot reset ({i+1}/{len(ALL_EXPRESSIONS)}) --")
            await asyncio.sleep(8)

async def demo_led():
    print("\n=== ĐÈN LED MIỆNG ===")

    print("  → Đèn xanh sáng cố định 3 giây")
    await SetMouthLamp(
        color=MouthLampColor.GREEN,
        mode=MouthLampMode.NORMAL,
        duration=3000
    ).execute()
    await asyncio.sleep(3.5)

    print("  → Đèn đỏ nhấp nháy")
    await SetMouthLamp(
        color=MouthLampColor.RED,
        mode=MouthLampMode.BREATH,
        duration=5000,
        breath_duration=800
    ).execute()
    await asyncio.sleep(5.5)

    print("  → Đèn trắng mãi mãi")
    await SetMouthLamp(
        color=MouthLampColor.WHITE,
        mode=MouthLampMode.NORMAL,
        duration=-1
    ).execute()
    await asyncio.sleep(2)

    print("  → Tắt đèn")
    await ControlMouthLamp(is_open=False).execute()

# ═══════════════════════════════════════════════
# 3. ACTION & NHẢY MÚA — cần StartRunProgram
# ═══════════════════════════════════════════════
async def demo_action():
    print("\n=== ACTION ===")
    actions = [
        ("011",        "Gật đầu"),
        ("015",        "Chào đón"),
        ("010",        "Cười"),
        ("037",        "Lắc đầu"),
        ("017",        "Giơ tay"),
        ("action_016", "Tạm biệt"),
    ]
    for name, label in actions:
        print(f"  → {label} ({name})")
        (_, resp) = await PlayAction(action_name=name).execute()
        print(f"     OK: {resp.isSuccess}")
        await asyncio.sleep(3)

async def demo_dance():
    print("\n=== NHẢY MÚA ===")
    dances = [
        ("dance_0004en", "Little Star"),
        ("dance_0006en", "Seaweed Dance"),
        ("dance_0009en", "Learn to Meow"),
    ]
    for name, label in dances:
        print(f"  → {label}")
        (_, resp) = await StartBehavior(name=name).execute()
        print(f"     OK: {resp.isSuccess}")
        await asyncio.sleep(5)
        await StopBehavior().execute()
        await asyncio.sleep(1.5)

# ═══════════════════════════════════════════════
# 4. DI CHUYỂN — cần StartRunProgram
# ═══════════════════════════════════════════════
async def demo_move():
    print("\n=== DI CHUYỂN ===")
    moves = [
        (MoveRobotDirection.FORWARD,   3, "Tiến 3 bước"),
        (MoveRobotDirection.BACKWARD,  3, "Lùi 3 bước"),
        (MoveRobotDirection.LEFTWARD,  3, "Trái 3 bước"),
        (MoveRobotDirection.RIGHTWARD, 3, "Phải 3 bước"),
    ]
    for direction, step, label in moves:
        print(f"  → {label}")
        (_, resp) = await MoveRobot(step=step, direction=direction).execute()
        print(f"     OK: {resp.isSuccess}")
        await asyncio.sleep(3)

# ═══════════════════════════════════════════════
# 5. NHẬN DIỆN — cần StartRunProgram
# ═══════════════════════════════════════════════
async def demo_face():
    print("\n=== NHẬN DIỆN KHUÔN MẶT ===")

    print("  → Đếm khuôn mặt (timeout 10s)...")
    (_, resp) = await FaceDetect(timeout=10).execute()
    if resp.isSuccess:
        print(f"     Phát hiện {resp.count} khuôn mặt")
    else:
        print(f"     Lỗi: {resp.resultCode}")

    print("  → Nhận diện danh tính (timeout 10s)...")
    (_, resp) = await FaceRecognise(timeout=10).execute()
    if resp.isSuccess:
        for face in resp.faceInfos:
            name = face.name if face.name != "stranger" else "Người lạ"
            print(f"     Tên: {name}, Tuổi: {face.age}")
    else:
        print(f"     Lỗi: {resp.resultCode}")

async def demo_object():
    print("\n=== NHẬN DIỆN VẬT THỂ ===")

    print("  → Nhận dạng cử chỉ tay (timeout 10s)...")
    (_, resp) = await ObjectRecognise(
        object_type=ObjectRecogniseType.GESTURE, timeout=10
    ).execute()
    if resp.isSuccess:
        print(f"     Cử chỉ: {resp.objects}")
    else:
        print(f"     Lỗi: {resp.resultCode}")

    print("  → Chụp ảnh ngay...")
    (_, resp) = await TakePicture(
        take_picture_type=TakePictureType.IMMEDIATELY
    ).execute()
    if resp.isSuccess:
        print(f"     Ảnh lưu tại: {resp.picPath}")
    else:
        print(f"     Lỗi: {resp.resultCode}")

# ═══════════════════════════════════════════════
# 6. KẾT HỢP NÓI + BIỂU CẢM + ACTION
#    Cần: pip install gtts + python file_server.py
#    Quy trình mỗi màn:
#      set_expression (không cần StartRunProgram)
#      → StartRunProgram → noi() + action
#      → reconnect() để reset cho màn tiếp theo
# ═══════════════════════════════════════════════
async def demo_ket_hop():
    print("\n=== KẾT HỢP NÓI + BIỂU CẢM + ACTION ===")

    # Màn 1: Chào
    print("\n[Màn 1: Chào]")
    await set_expression("codemao10", "Hứng khởi")
    await asyncio.sleep(1)
    await StartRunProgram().execute()
    await asyncio.sleep(4)
    await noi("Xin chào! Tôi là Alpha Mini.")
    await PlayAction(action_name="015").execute()
    await asyncio.sleep(3)

    # Màn 2: Nhảy
    print("\n[Màn 2: Nhảy]")
    if not await reconnect(): return
    await set_expression("codemao11", "Tinh thần chiến đấu")
    await asyncio.sleep(1)
    await StartRunProgram().execute()
    await asyncio.sleep(4)
    await noi("Bây giờ tôi sẽ nhảy cho bạn xem!")
    await StartBehavior(name="dance_0004en").execute()
    await asyncio.sleep(6)
    await StopBehavior().execute()
    await asyncio.sleep(2)

    # Màn 3: Tạm biệt
    print("\n[Màn 3: Tạm biệt]")
    if not await reconnect(): return
    await set_expression("codemao19", "Yêu")
    await asyncio.sleep(1)
    await StartRunProgram().execute()
    await asyncio.sleep(4)
    await noi("Tạm biệt! Hẹn gặp lại bạn nhé.")
    await PlayAction(action_name="action_016").execute()
    await asyncio.sleep(3)

# ═══════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════
async def main():
    get_pc_ip()
    print(f"IP máy tính: {PC_IP}")

    device = await MiniSdk.get_device_by_name(SERIAL, timeout=10)
    if not device:
        print("Không tìm thấy robot!"); return

    await MiniSdk.connect(device)
    print(f"Đã kết nối: {device.name} @ {device.address}")
    await asyncio.sleep(2)

    # ════════════════════════════════════════════
    # Bỏ comment dòng muốn chạy, comment các dòng còn lại
    # ════════════════════════════════════════════

    await demo_expression()           # Xem 52 biểu cảm (không cần StartRunProgram)
    await demo_led()                  # Đèn LED miệng (không cần StartRunProgram)

    await StartRunProgram().execute() # Bắt buộc trước các demo bên dưới
    await asyncio.sleep(6)
    await demo_action()               # Action
    await demo_dance()                # Nhảy múa
    await demo_move()                 # Di chuyển
    await demo_face()                 # Nhận diện khuôn mặt
    await demo_object()               # Nhận diện vật thể + chụp ảnh

    # await demo_ket_hop()            # TTS + biểu cảm + action kết hợp
    #                                 # (cần: pip install gtts + python file_server.py)

    # ════════════════════════════════════════════

    await asyncio.sleep(1)
    await MiniSdk.release()
    print("\nHoàn thành!")

asyncio.run(main())