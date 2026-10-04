"""
system_tools.py — เครื่องมือควบคุม Windows สำหรับ Gemini Function Calling

ฟังก์ชันทั้งหมดในไฟล์นี้จะถูกส่งให้ Gemini เป็น tools
Gemini จะเรียกใช้อัตโนมัติเมื่อผู้ใช้สั่งด้วยเสียง
"""

import os
import sys
import json
import datetime
import webbrowser
import ctypes
import subprocess
from pathlib import Path
from urllib.parse import quote_plus
from typing import Optional, Callable
import psutil

# ─── Volume Control (pycaw) ───

def _get_volume_interface():
    """สร้าง IAudioEndpointVolume interface สำหรับควบคุมเสียง"""
    from pycaw.pycaw import AudioUtilities

    device = AudioUtilities.GetSpeakers()
    return device.EndpointVolume


def get_volume() -> str:
    """อ่านระดับเสียงปัจจุบันของระบบ

    Returns:
        ข้อความแจ้งระดับเสียงปัจจุบัน เช่น "ระดับเสียงปัจจุบัน: 50%"
    """
    try:
        volume = _get_volume_interface()
        level = int(volume.GetMasterVolumeLevelScalar() * 100)
        return f"ระดับเสียงปัจจุบัน: {level}%"
    except Exception as e:
        return f"ไม่สามารถอ่านระดับเสียงได้: {e}"


def set_volume(level: int) -> str:
    """ตั้งระดับเสียงของระบบ

    Args:
        level: ระดับเสียงที่ต้องการ (0-100)

    Returns:
        ข้อความยืนยันผลลัพธ์
    """
    try:
        level = max(0, min(100, level))
        volume = _get_volume_interface()
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        return f"ปรับเสียงเป็น {level}% เรียบร้อยแล้ว"
    except Exception as e:
        return f"ไม่สามารถตั้งระดับเสียงได้: {e}"


def adjust_volume(change: int) -> str:
    """เพิ่มหรือลดระดับเสียงตามจำนวนที่กำหนด

    Args:
        change: จำนวนที่ต้องการเพิ่ม (บวก) หรือลด (ลบ) เช่น 10 หรือ -20

    Returns:
        ข้อความยืนยันผลลัพธ์
    """
    try:
        volume = _get_volume_interface()
        current = volume.GetMasterVolumeLevelScalar() * 100
        new_level = max(0, min(100, int(current + change)))
        volume.SetMasterVolumeLevelScalar(new_level / 100.0, None)
        return f"ปรับเสียงจาก {int(current)}% เป็น {new_level}% เรียบร้อยแล้ว"
    except Exception as e:
        return f"ไม่สามารถปรับเสียงได้: {e}"


def toggle_mute() -> str:
    """เปิด/ปิดเสียง (mute/unmute)

    Returns:
        ข้อความแจ้งสถานะ mute ปัจจุบัน
    """
    try:
        volume = _get_volume_interface()
        is_muted = volume.GetMute()
        volume.SetMute(not is_muted, None)
        status = "ปิดเสียง (mute)" if not is_muted else "เปิดเสียง (unmute)"
        return f"{status} เรียบร้อยแล้ว"
    except Exception as e:
        return f"ไม่สามารถสลับ mute ได้: {e}"


# ─── Brightness Control ───

def get_brightness() -> str:
    """อ่านระดับความสว่างหน้าจอปัจจุบัน

    Returns:
        ข้อความแจ้งระดับความสว่างปัจจุบัน
    """
    try:
        import screen_brightness_control as sbc
        brightness = sbc.get_brightness()
        # sbc.get_brightness() อาจ return list ถ้ามีหลายจอ
        if isinstance(brightness, list):
            brightness = brightness[0]
        return f"ความสว่างหน้าจอปัจจุบัน: {brightness}%"
    except Exception as e:
        return f"ไม่สามารถอ่านความสว่างได้: {e}"


def set_brightness(level: int) -> str:
    """ตั้งระดับความสว่างหน้าจอ

    Args:
        level: ระดับความสว่าง (0-100)

    Returns:
        ข้อความยืนยันผลลัพธ์
    """
    try:
        import screen_brightness_control as sbc
        level = max(0, min(100, level))
        sbc.set_brightness(level)
        return f"ปรับความสว่างเป็น {level}% เรียบร้อยแล้ว"
    except Exception as e:
        return f"ไม่สามารถตั้งความสว่างได้: {e}"


def adjust_brightness(change: int) -> str:
    """เพิ่มหรือลดความสว่างหน้าจอ

    Args:
        change: จำนวนที่ต้องการเพิ่ม (บวก) หรือลด (ลบ) เช่น 10 หรือ -20

    Returns:
        ข้อความยืนยันผลลัพธ์
    """
    try:
        import screen_brightness_control as sbc
        current = sbc.get_brightness()
        if isinstance(current, list):
            current = current[0]
        new_level = max(0, min(100, current + change))
        sbc.set_brightness(new_level)
        return f"ปรับความสว่างจาก {current}% เป็น {new_level}% เรียบร้อยแล้ว"
    except Exception as e:
        return f"ไม่สามารถปรับความสว่างได้: {e}"


# ─── Web & Media ───

def open_youtube() -> str:
    """เปิดเว็บไซต์ YouTube ใน browser

    Returns:
        ข้อความยืนยัน
    """
    try:
        webbrowser.open("https://www.youtube.com")
        return "เปิด YouTube เรียบร้อยแล้ว"
    except Exception as e:
        return f"ไม่สามารถเปิด YouTube ได้: {e}"


def search_google(query: str) -> str:
    """ค้นหาข้อมูลใน Google

    Args:
        query: คำค้นหา

    Returns:
        ข้อความยืนยัน
    """
    try:
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        webbrowser.open(url)
        return f"ค้นหา '{query}' ใน Google เรียบร้อยแล้ว"
    except Exception as e:
        return f"ไม่สามารถค้นหาได้: {e}"


def search_youtube(query: str) -> str:
    """ค้นหาวิดีโอใน YouTube

    Args:
        query: คำค้นหา

    Returns:
        ข้อความยืนยัน
    """
    try:
        url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        webbrowser.open(url)
        return f"ค้นหา '{query}' ใน YouTube เรียบร้อยแล้ว"
    except Exception as e:
        return f"ไม่สามารถค้นหาได้: {e}"


def open_website(url: str) -> str:
    """เปิดเว็บไซต์ที่ระบุใน browser

    Args:
        url: URL ของเว็บไซต์ที่ต้องการเปิด

    Returns:
        ข้อความยืนยัน
    """
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        webbrowser.open(url)
        return f"เปิดเว็บไซต์ {url} เรียบร้อยแล้ว"
    except Exception as e:
        return f"ไม่สามารถเปิดเว็บไซต์ได้: {e}"


def play_pause_media() -> str:
    """กดปุ่ม Play/Pause สื่อ (Media key)

    Returns:
        ข้อความยืนยัน
    """
    try:
        VK_MEDIA_PLAY_PAUSE = 0xB3
        KEYEVENTF_EXTENDEDKEY = 0x0001
        KEYEVENTF_KEYUP = 0x0002
        ctypes.windll.user32.keybd_event(
            VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_EXTENDEDKEY, 0
        )
        ctypes.windll.user32.keybd_event(
            VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0
        )
        return "กด Play/Pause เรียบร้อยแล้ว"
    except Exception as e:
        return f"ไม่สามารถกด Play/Pause ได้: {e}"


def next_track() -> str:
    """ข้ามไปเพลง/วิดีโอถัดไป (Media Next Track)

    Returns:
        ข้อความยืนยัน
    """
    try:
        VK_MEDIA_NEXT_TRACK = 0xB0
        KEYEVENTF_EXTENDEDKEY = 0x0001
        KEYEVENTF_KEYUP = 0x0002
        ctypes.windll.user32.keybd_event(
            VK_MEDIA_NEXT_TRACK, 0, KEYEVENTF_EXTENDEDKEY, 0
        )
        ctypes.windll.user32.keybd_event(
            VK_MEDIA_NEXT_TRACK, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0
        )
        return "ข้ามไปเพลงถัดไปเรียบร้อยแล้ว"
    except Exception as e:
        return f"ไม่สามารถข้ามเพลงได้: {e}"


def previous_track() -> str:
    """ย้อนกลับไปเพลง/วิดีโอก่อนหน้า (Media Previous Track)

    Returns:
        ข้อความยืนยัน
    """
    try:
        VK_MEDIA_PREV_TRACK = 0xB1
        KEYEVENTF_EXTENDEDKEY = 0x0001
        KEYEVENTF_KEYUP = 0x0002
        ctypes.windll.user32.keybd_event(
            VK_MEDIA_PREV_TRACK, 0, KEYEVENTF_EXTENDEDKEY, 0
        )
        ctypes.windll.user32.keybd_event(
            VK_MEDIA_PREV_TRACK, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0
        )
        return "ย้อนกลับไปเพลงก่อนหน้าเรียบร้อยแล้ว"
    except Exception as e:
        return f"ไม่สามารถย้อนเพลงได้: {e}"


# ─── Power Control ───

def shutdown_pc(delay: int = 60) -> str:
    """ปิดเครื่องคอมพิวเตอร์ (มี delay เพื่อให้ยกเลิกได้ทัน)

    Args:
        delay: ระยะเวลา delay ก่อนปิดเครื่อง (วินาที) ค่าเริ่มต้น 60 วินาที

    Returns:
        ข้อความยืนยัน
    """
    try:
        delay = max(10, int(delay))  # อย่างน้อย 10 วินาที
        subprocess.run(["shutdown", "/s", "/t", str(delay)], check=False, shell=False)
        return (
            f"กำลังจะปิดเครื่องใน {delay} วินาที "
            f"สั่ง 'ยกเลิกการปิดเครื่อง' เพื่อยกเลิกได้ครับ"
        )
    except Exception as e:
        return f"ไม่สามารถสั่งปิดเครื่องได้: {e}"


def restart_pc(delay: int = 60) -> str:
    """รีสตาร์ทคอมพิวเตอร์ (มี delay เพื่อให้ยกเลิกได้ทัน)

    Args:
        delay: ระยะเวลา delay ก่อนรีสตาร์ท (วินาที) ค่าเริ่มต้น 60 วินาที

    Returns:
        ข้อความยืนยัน
    """
    try:
        delay = max(10, int(delay))
        subprocess.run(["shutdown", "/r", "/t", str(delay)], check=False, shell=False)
        return (
            f"กำลังจะรีสตาร์ทใน {delay} วินาที "
            f"สั่ง 'ยกเลิกการปิดเครื่อง' เพื่อยกเลิกได้ครับ"
        )
    except Exception as e:
        return f"ไม่สามารถสั่งรีสตาร์ทได้: {e}"


def cancel_shutdown() -> str:
    """ยกเลิกคำสั่งปิดเครื่อง/รีสตาร์ทที่กำลังนับเวลาอยู่

    Returns:
        ข้อความยืนยัน
    """
    try:
        subprocess.run(["shutdown", "/a"], check=False, shell=False)
        return "ยกเลิกการปิดเครื่อง/รีสตาร์ทเรียบร้อยแล้ว"
    except Exception as e:
        return f"ไม่สามารถยกเลิกได้: {e}"


def exit_assistant() -> str:
    """ปิดการทำงานของโปรแกรมผู้ช่วยมหาปราชญ์ราฟาเอล (ออกจากโปรแกรม/ปิดตัวเอง)

    Returns:
        ข้อความลาก่อน
    """
    import threading
    import time

    def _delayed_exit():
        time.sleep(2.0)  # รอให้พูดประโยคลาก่อนจบก่อนปิดโปรแกรม
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.quit()
        else:
            os._exit(0)

    threading.Thread(target=_delayed_exit, daemon=True).start()
    return "รับทราบครับ กำลังปิดระบบราฟาเอล ขอให้ท่านเจ้านายมีวันที่ดีครับ"


# ─── Memory Storage ───
_MEMORY_FILE = Path(__file__).parent / "user_memory.json"

def _load_memory() -> dict:
    if _MEMORY_FILE.exists():
        try:
            with open(_MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_memory(data: dict) -> None:
    try:
        with open(_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def remember_info(key: str, value: str) -> str:
    """บันทึกข้อมูลส่วนตัวหรือความจำระยะยาวของท่านเจ้านาย เช่น สิ่งที่ชอบ, งานที่ทำ, โน้ตเตือนความจำ

    Args:
        key: หัวข้อหรือเรื่องที่ต้องการจำ เช่น "เครื่องดื่มที่ชอบ", "โปรเจคปัจจุบัน", "วันสำคัญ"
        value: รายละเอียดข้อมูลที่ต้องการจำ เช่น "กาแฟดำไม่ใส่น้ำตาล"

    Returns:
        ข้อความยืนยันการบันทึก
    """
    mem = _load_memory()
    mem[key.strip()] = value.strip()
    _save_memory(mem)
    return f"รายงาน: ได้บันทึกข้อมูล '{key}' เรียบร้อยแล้วครับ"


def recall_info(key: str) -> str:
    """ดึงข้อมูลความจำหรือสิ่งที่เคยบันทึกไว้ของท่านเจ้านาย

    Args:
        key: หัวข้อที่ต้องการค้นหา เช่น "เครื่องดื่มที่ชอบ", "โปรเจค" หรือ "ทั้งหมด"

    Returns:
        ข้อมูลที่ค้นพบ
    """
    mem = _load_memory()
    if not mem:
        return "รายงาน: ยังไม่มีข้อมูลใดๆ บันทึกอยู่ในความทรงจำครับ"

    if key.strip() in ("ทั้งหมด", "all", "*", ""):
        items = [f"- {k}: {v}" for k, v in mem.items()]
        return "รายงานความทรงจำทั้งหมด:\n" + "\n".join(items)

    for k, v in mem.items():
        if key.lower() in k.lower():
            return f"รายงานผลการค้นหา: สำหรับ '{k}' คือ '{v}' ครับ"

    return f"รายงาน: ไม่พบข้อมูลที่ตรงกับ '{key}' ในความทรงจำครับ"


def open_application(app_name: str) -> str:
    """เปิดโปรแกรม แอปพลิเคชัน หรือเครื่องมือบนคอมพิวเตอร์ Windows

    Args:
        app_name: ชื่อโปรแกรมที่ต้องการเปิด เช่น "vscode", "chrome", "notepad", "calculator", "task manager", "settings", "spotify", "discord", "steam", "explorer"

    Returns:
        ข้อความยืนยันผลลัพธ์
    """
    app_lower = app_name.lower().strip()
    app_map = {
        "calculator": "calc.exe",
        "เครื่องคิดเลข": "calc.exe",
        "notepad": "notepad.exe",
        "สมุดจด": "notepad.exe",
        "โน้ต": "notepad.exe",
        "vscode": "code",
        "vs code": "code",
        "visual studio code": "code",
        "วีเอสโค้ด": "code",
        "task manager": "taskmgr.exe",
        "ตัวจัดการงาน": "taskmgr.exe",
        "settings": "start ms-settings:",
        "การตั้งค่า": "start ms-settings:",
        "explorer": "explorer.exe",
        "ไฟล์": "explorer.exe",
        "cmd": "start cmd.exe",
        "terminal": "start wt.exe",
        "paint": "mspaint.exe",
        "วาดรูป": "mspaint.exe",
        "spotify": "start spotify:",
        "discord": "start discord:",
        "steam": "start steam:",
        "chrome": "start chrome",
        "edge": "start msedge",
    }

    cmd = None
    for k, v in app_map.items():
        if k in app_lower:
            cmd = v
            break

    try:
        if cmd:
            subprocess.Popen(cmd, shell=True)
            return f"รายงาน: กำลังเปิด {app_name} เรียบร้อยแล้วครับ"
        else:
            # กรองชื่อโปรแกรมให้มีเฉพาะอักขระปลอดภัย ป้องกัน Command Injection
            safe_app = "".join(c for c in app_lower if c.isalnum() or c in ("-", "_", ".", " "))
            if not safe_app:
                return f"รายงาน: ชื่อโปรแกรม '{app_name}' ไม่ถูกต้องหรือไม่ปลอดภัยครับ"
            subprocess.Popen(["cmd.exe", "/c", "start", "", safe_app], shell=False)
            return f"รายงาน: กำลังเรียกเปิด {app_name} ครับ"
    except Exception as e:
        return f"ไม่สามารถเปิด {app_name} ได้: {e}"


def close_application(app_name: str) -> str:
    """ปิดโปรแกรมหรือกระบวนการที่กำลังทำงานอยู่

    Args:
        app_name: ชื่อโปรแกรมหรือ process เช่น "chrome", "notepad", "code", "spotify"

    Returns:
        ข้อความรายงานผล
    """
    try:
        app_lower = app_name.lower().replace(".exe", "").strip()
        closed_count = 0
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                pname = proc.info['name'].lower()
                if app_lower in pname:
                    proc.terminate()
                    closed_count += 1
            except Exception:
                pass
        if closed_count > 0:
            return f"รายงาน: ปิดโปรแกรม {app_name} ({closed_count} กระบวนการ) เรียบร้อยแล้วครับ"
        else:
            # กรองชื่อ process ให้มีเฉพาะตัวอักษรที่ปลอดภัย
            safe_name = "".join(c for c in app_lower if c.isalnum() or c in ("-", "_", "."))
            if safe_name:
                subprocess.run(
                    ["taskkill", "/f", "/im", f"{safe_name}.exe"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    shell=False,
                )
            return f"รายงาน: ดำเนินการส่งคำสั่งปิด {app_name} เรียบร้อยแล้วครับ"
    except Exception as e:
        return f"ไม่สามารถปิด {app_name} ได้: {e}"


def take_screenshot() -> str:
    """ถ่ายภาพหน้าจอ (Screenshot) บันทึกลงโฟลเดอร์ Pictures/Screenshots

    Returns:
        ข้อความยืนยันพร้อมตำแหน่งไฟล์
    """
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        screen = QApplication.primaryScreen()
        if not screen:
            return "ไม่สามารถตรวจจับหน้าจอได้"
        pix = screen.grabWindow(0)

        pic_dir = Path(os.environ.get("USERPROFILE", "")) / "Pictures" / "Screenshots"
        pic_dir.mkdir(parents=True, exist_ok=True)
        filename = f"Screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = pic_dir / filename
        pix.save(str(filepath))
        return f"รายงาน: บันทึกภาพหน้าจอเรียบร้อยแล้วที่ {filename}"
    except Exception as e:
        return f"ไม่สามารถแคปหน้าจอได้: {e}"


def get_system_status() -> str:
    """ตรวจสอบสถานะระบบคอมพิวเตอร์แบบ Real-time: CPU, RAM, Disk, แบตเตอรี่

    Returns:
        รายงานผลการวิเคราะห์สถานะเครื่อง
    """
    try:
        cpu = psutil.cpu_percent(interval=0.2)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('C:')
        batt = psutil.sensors_battery()

        batt_str = f"{batt.percent}% ({'กำลังชาร์จ' if batt.power_plugged else 'ใช้แบตเตอรี่'})" if batt else "ไม่มีแบตเตอรี่"

        return (
            f"รายงานสถานะระบบ:\n"
            f"- ซีพียู (CPU): ใช้งาน {cpu}%\n"
            f"- แรม (RAM): ใช้งาน {mem.percent}% ({mem.used // (1024**2)} MB / {mem.total // (1024**2)} MB)\n"
            f"- พื้นที่ไดรฟ์ C: ว่าง {disk.free // (1024**3)} GB จาก {disk.total // (1024**3)} GB\n"
            f"- แบตเตอรี่: {batt_str}"
        )
    except Exception as e:
        return f"ไม่สามารถตรวจสอบสถานะระบบได้: {e}"


def get_battery_status() -> str:
    """ตรวจสอบระดับพลังงานแบตเตอรี่และสถานะการชาร์จ

    Returns:
        ข้อความแจ้งสถานะแบตเตอรี่
    """
    try:
        batt = psutil.sensors_battery()
        if not batt:
            return "รายงาน: อุปกรณ์นี้เป็นคอมพิวเตอร์ตั้งโต๊ะ หรือไม่มีเซนเซอร์แบตเตอรี่ครับ"
        status = "กำลังเชื่อมต่อสายชาร์จ" if batt.power_plugged else "กำลังใช้งานจากแบตเตอรี่"
        return f"รายงาน: แบตเตอรี่เหลือ {batt.percent}% สถานะ: {status} ครับ"
    except Exception as e:
        return f"ไม่สามารถตรวจสอบแบตเตอรี่ได้: {e}"


def lock_pc() -> str:
    """ล็อคหน้าจอคอมพิวเตอร์ Windows ทันที (Lock Workstation)

    Returns:
        ข้อความยืนยัน
    """
    try:
        ctypes.windll.user32.LockWorkStation()
        return "รายงาน: ดำเนินการล็อคหน้าจอเรียบร้อยแล้วครับ"
    except Exception as e:
        return f"ไม่สามารถล็อคหน้าจอได้: {e}"


def minimize_all_windows() -> str:
    """ย่อหน้าต่างทั้งหมดกลับสู่หน้าเดสก์ท็อป (Show Desktop)

    Returns:
        ข้อความยืนยัน
    """
    try:
        VK_LWIN = 0x5B
        VK_D = 0x44
        KEYEVENTF_KEYUP = 0x0002
        user32 = ctypes.windll.user32
        user32.keybd_event(VK_LWIN, 0, 0, 0)
        user32.keybd_event(VK_D, 0, 0, 0)
        user32.keybd_event(VK_D, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)
        return "รายงาน: ย่อหน้าต่างทั้งหมดกลับสู่หน้าจอ Desktop เรียบร้อยแล้วครับ"
    except Exception as e:
        return f"ไม่สามารถย่อหน้าต่างได้: {e}"


def get_current_time_date() -> str:
    """บอกวันและเวลาปัจจุบัน

    Returns:
        ข้อความแจ้งวัน เวลา วันที่ เดือน ปี
    """
    now = datetime.datetime.now()
    days_th = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
    months_th = [
        "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
        "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
    ]
    day_name = days_th[now.weekday()]
    month_name = months_th[now.month - 1]
    year_be = now.year + 543
    time_str = now.strftime("%H นาฬิกา %M นาที")
    return f"รายงาน: ขณะนี้เวลา {time_str} วัน{day_name} ที่ {now.day} {month_name} พุทธศักราช {year_be} ครับ"


def get_clipboard_text() -> str:
    """อ่านข้อความล่าสุดที่คัดลอก (Copy) ไว้ในคลิปบอร์ด

    Returns:
        ข้อความในคลิปบอร์ด
    """
    try:
        text = ""
        # 1. ลองอ่านผ่าน PyQt6 หากมี GUI Application instance
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                cb = QApplication.clipboard()
                if cb:
                    text = cb.text()
        except Exception:
            pass

        # 2. หากยังไม่ได้ข้อความ ให้ fallback ไปยัง Windows Native Clipboard API
        if not text:
            try:
                from ctypes import wintypes
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                CF_UNICODETEXT = 13
                if user32.OpenClipboard(None):
                    h_mem = user32.GetClipboardData(CF_UNICODETEXT)
                    if h_mem:
                        kernel32.GlobalLock.restype = wintypes.LPWSTR
                        p_str = kernel32.GlobalLock(h_mem)
                        if p_str:
                            text = str(p_str)
                            kernel32.GlobalUnlock(h_mem)
                    user32.CloseClipboard()
            except Exception:
                pass

        if not text or not text.strip():
            return "รายงาน: คลิปบอร์ดว่างเปล่า ไม่มีข้อความที่คัดลอกไว้ครับ"
        preview = text.strip()[:150] + "..." if len(text.strip()) > 150 else text.strip()
        return f"รายงาน: ข้อความในคลิปบอร์ดคือ: '{preview}'"
    except Exception as e:
        return f"ไม่สามารถอ่านคลิปบอร์ดได้: {e}"


def empty_recycle_bin() -> str:
    """ล้างไฟล์ในถังขยะ Windows (Empty Recycle Bin)

    Returns:
        ข้อความยืนยัน
    """
    try:
        ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 7)
        return "รายงาน: ดำเนินการล้างถังขยะของระบบเรียบร้อยแล้วครับ"
    except Exception as e:
        return f"ไม่สามารถล้างถังขยะได้: {e}"


def analyze_current_screen(question: str = "วิเคราะห์สิ่งที่อยู่บนหน้าจอโดยสรุป") -> str:
    """วิเคราะห์สิ่งที่ปรากฏอยู่บนหน้าจอคอมพิวเตอร์ปัจจุบันด้วยสายตา AI มหาปราชญ์ (Gemini Multimodal Vision)

    Args:
        question: คำถามหรือสิ่งที่ต้องการให้วิเคราะห์บนหน้าจอ เช่น "หน้าจอนี้เปิดอะไรอยู่", "สรุปหน้าเว็บนี้ให้ที", "ดูโค้ดบนจอว่ามี error อะไร", "ภาพนี้คืออะไร"

    Returns:
        ผลการวิเคราะห์สิ่งที่เห็นบนหน้าจอ
    """
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QBuffer, QIODevice, Qt
        from google import genai
        from google.genai import types
        import config

        app = QApplication.instance()
        screen = QApplication.primaryScreen()
        if not screen:
            return "รายงาน: ไม่สามารถตรวจจับหน้าจอเพื่อวิเคราะห์ได้ครับ"

        pix = screen.grabWindow(0)
        # ย่อขนาดความกว้างเหลือ 1024px เพื่อความรวดเร็วสูงสุดในการส่งและประมวลผล
        scaled_pix = pix.scaledToWidth(1024, Qt.TransformationMode.SmoothTransformation)

        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.ReadWrite)
        scaled_pix.save(buf, "JPEG", 75)
        img_bytes = bytes(buf.data())

        client = genai.Client(api_key=config.GEMINI_API_KEY)
        model_name = getattr(config, "GEMINI_MODEL", "gemini-3.5-flash-lite")

        prompt = (
            f"คุณคือราฟาเอล จงวิเคราะห์ภาพหน้าจอนี้อย่างชาญฉลาดและเฉียบคมเพื่อตอบคำถาม: '{question}'\n"
            "กฎสำคัญ:\n"
            "1. ตอบกระชับ คมชัด ตรงประเด็น 2-3 ประโยคเพื่อนำไปพูดเป็นเสียง (TTS)\n"
            "2. ขึ้นต้นด้วย 'รายงานผลการวิเคราะห์หน้าจอ:'\n"
            "3. ระบุชื่อโปรแกรม หน้าต่าง หรือเนื้อหาสำคัญที่ปรากฏอย่างชัดเจน"
        )

        res = client.models.generate_content(
            model=model_name,
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                prompt,
            ],
        )

        result = res.text.strip() if (res and res.text) else "ไม่สามารถระบุเนื้อหาบนหน้าจอได้ชัดเจนครับ"
        return result
    except Exception as e:
        return f"ไม่สามารถวิเคราะห์หน้าจอได้: {e}"


def search_web_instant(query: str) -> str:
    """ค้นหาข้อมูลสรุป ข้อเท็จจริง หรือคำตอบแบบเร่งด่วนจากสารานุกรมและอินเทอร์เน็ต (Instant Knowledge Lookup)

    Args:
        query: คำถามหรือหัวข้อที่ต้องการค้นหา เช่น "บิตคอยน์คืออะไร", "ทฤษฎีสัมพัทธภาพ", "Python คืออะไร"

    Returns:
        เนื้อหาข้อมูลสรุปที่ค้นพบ
    """
    try:
        import urllib.request
        import urllib.parse

        encoded = urllib.parse.quote_plus(query)

        # 1. ลองค้นหาผ่าน DuckDuckGo Instant Answer API
        try:
            ddg_url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
            req = urllib.request.Request(ddg_url, headers={"User-Agent": "RaphaelWisdom/1.0"})
            with urllib.request.urlopen(req, timeout=4) as response:
                data = json.loads(response.read().decode("utf-8"))
            abstract = data.get("AbstractText", "") or data.get("Abstract", "")
            if abstract:
                return f"รายงานข้อมูลจากแหล่งความรู้: {abstract}"
        except Exception:
            pass

        # 2. หากไม่พบใน DuckDuckGo ให้ลอง Wikipedia API ภาษาไทย
        try:
            wiki_url = f"https://th.wikipedia.org/api/rest_v1/page/summary/{encoded}"
            req_wiki = urllib.request.Request(wiki_url, headers={"User-Agent": "RaphaelWisdom/1.0"})
            with urllib.request.urlopen(req_wiki, timeout=4) as wiki_res:
                wiki_data = json.loads(wiki_res.read().decode("utf-8"))
                extract = wiki_data.get("extract", "")
                if extract:
                    return f"รายงานข้อมูลจากสารานุกรม: {extract[:350]}"
        except Exception:
            pass

        # 3. หากยังไม่พบคำตอบสรุปตรงๆ ให้เปิดค้นหาใน Google เบราว์เซอร์ให้แทน
        search_google(query)
        return f"รายงาน: ได้เปิดหน้าค้นหา Google สำหรับ '{query}' ให้ท่านเจ้านายบนเบราว์เซอร์แล้วครับ"
    except Exception as e:
        search_google(query)
        return f"รายงาน: ได้เปิดหน้าค้นหา Google สำหรับ '{query}' ให้ท่านเจ้านายแล้วครับ ({e})"


# ─── Theme & Autostart Management ───
_theme_change_callback: Optional[Callable[[str], bool]] = None

def register_theme_callback(cb: Callable[[str], bool]) -> None:
    global _theme_change_callback
    _theme_change_callback = cb

def switch_gui_theme(theme_name: str) -> str:
    """เปลี่ยนธีมสีของวงแหวนเวทมนตร์ราฟาเอลบนหน้าจอ

    Args:
        theme_name: ชื่อธีมสี เช่น 'raphael' หรือ 'ทอง' (สีทองอำพัน/แดงชาด), 'rimuru' หรือ 'ฟ้า' (สีฟ้าครามสไลม์), 'demon_lord' หรือ 'ม่วง' (สีม่วงจอมมาร), 'forest' หรือ 'เขียว' (สีเขียวมรกตเอลฟ์), 'solar' หรือ 'แดง' (สีแดงเพลิงสุริยัน)
    """
    global _theme_change_callback
    if _theme_change_callback:
        success = _theme_change_callback(theme_name)
        if success:
            return f"รายงาน: ได้เปลี่ยนธีมสีของวงเวทย์เป็น '{theme_name}' ตามบัญชาของท่านเจ้านายแล้วครับ"
    return f"รายงาน: รับทราบคำสั่งเปลี่ยนธีมสี '{theme_name}' เรียบร้อยแล้วครับ"

def set_windows_autostart(enable: bool) -> str:
    """ตั้งค่าให้ราฟาเอลเริ่มทำงานอัตโนมัติเมื่อเปิดเครื่องคอมพิวเตอร์ (Windows Startup)

    Args:
        enable: True เพื่อเปิดให้เริ่มทำงานอัตโนมัติพร้อม Windows, False เพื่อยกเลิก
    """
    import winreg
    reg_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "TheGreatSageRaphael"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_key, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                cmd = f'"{sys.executable}" "{Path(__file__).parent / "main.py"}"'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
                return "รายงาน: ได้ตั้งค่าให้ราฟาเอลเริ่มทำงานอัตโนมัติเมื่อเปิดเครื่อง Windows เรียบร้อยแล้วครับ ท่านเจ้านาย"
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
                return "รายงาน: ได้ยกเลิกการเริ่มทำงานอัตโนมัติเมื่อเปิดเครื่องแล้วครับ ท่านเจ้านาย"
    except Exception as e:
        return f"รายงาน: ไม่สามารถตั้งค่า Autostart ได้เนื่องจาก: {e}"


# ─── รายชื่อ tools ทั้งหมดสำหรับส่งให้ Gemini ───

ALL_TOOLS: list = [
    get_volume,
    set_volume,
    adjust_volume,
    toggle_mute,
    get_brightness,
    set_brightness,
    adjust_brightness,
    open_youtube,
    search_google,
    search_youtube,
    search_web_instant,
    open_website,
    play_pause_media,
    next_track,
    previous_track,
    shutdown_pc,
    restart_pc,
    cancel_shutdown,
    exit_assistant,
    open_application,
    close_application,
    take_screenshot,
    analyze_current_screen,
    get_system_status,
    get_battery_status,
    lock_pc,
    minimize_all_windows,
    get_current_time_date,
    get_clipboard_text,
    empty_recycle_bin,
    remember_info,
    recall_info,
    switch_gui_theme,
    set_windows_autostart,
]
