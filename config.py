"""
config.py — การตั้งค่าทั้งหมดของ Great Sage Raphael

โหลด API key จาก .env และเก็บค่าคงที่สำหรับทุก module
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# ─── โหลด .env ───
_env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path)

# ─── API Keys ───
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# ─── Gemini Model (Ultra Low-Latency Voice AI) ───
GEMINI_MODEL: str = "gemini-3.5-flash-lite"
GEMINI_FALLBACK_MODELS: list[str] = [
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
]

# ─── Whisper (STT) ───
WHISPER_MODEL_SIZE: str = "medium"
WHISPER_DEVICE: str = "cuda"          # RTX 4060 — ใช้ GPU
WHISPER_COMPUTE_TYPE: str = "float16" # VRAM 16 GB เหลือเฟือ
WHISPER_LANGUAGE: str = "th"
WHISPER_BEAM_SIZE: int = 1            # Greedy search 3x เร็วกว่า beam=5 หน่วงเวลาเพียง ~0.25s
WHISPER_VAD_FILTER: bool = True       # ใช้ VAD filter มาตรฐาน
WHISPER_INITIAL_PROMPT: str = (
    "คำสั่งเสียงภาษาไทย ราฟาเอล: ราฟาเอล, เปิด YouTube, เปิด Chrome, "
    "ปรับเสียง, เพิ่มเสียง, ลดเสียง, ปิดเสียง, ปรับแสง, ลดแสง, เพิ่มแสง, "
    "แคปหน้าจอ, แบตเตอรี่, ปิดเครื่อง, รีสตาร์ท, ตอนนี้กี่โมง, วันนี้วันที่เท่าไหร่, "
    "เปิดเพลง, หยุดเพลง, เล่นเพลง, เปิดเว็บ Google, ค้นหา"
)

# ─── TTS ───
TTS_VOICE: str = "th-TH-PremwadeeNeural"  # เสียงหญิงไทย
TTS_RATE: str = "+0%"                      # ความเร็วปกติ
TTS_TEMP_DIR: str = str(Path(__file__).parent / "_tts_cache")
TTS_FALLBACK_ENABLED: bool = False   # ห้าม fallback ไปเสียงอื่น — ล็อก Premwadee เท่านั้น
TTS_TIMEOUT: float = 10.0           # timeout พื้นฐาน (วินาที) — ข้อความยาวจะ +0.03s ต่ออักขระ

# ─── Audio Recording & VAD ───
INPUT_DEVICE: Optional[str | int] = "default"  # "default" = ไมโครโฟนเริ่มต้นของระบบ (Windows Default Microphone)
INPUT_DEVICE_INDEX: Optional[int] = None       # เจาะจง Device Index (ถ้าต้องการ) หรือปล่อย None/"default"
SAMPLE_RATE: int = 16000        # Hz — มาตรฐานสำหรับ Whisper
CHANNELS: int = 1               # Mono
RECORD_CHUNK_SEC: float = 2.5   # ตรวจจับ wake word พื้นหลัง
VAD_SILENCE_TIMEOUT: float = 0.65 # หยุดบันทึกคำสั่งทันทีเมื่อผู้ใช้หยุดพูดเกิน 0.65 วินาที
VAD_MAX_RECORD_SEC: float = 4.5   # ระยะเวลาบันทึกสูงสุด (วินาที)


# ─── Wake Word ───
WAKE_WORD: str = "ราฟาเอล"
WAKE_WORD_ALTERNATIVES: list[str] = [
    "ราฟาเอล",
    "ร่า ฟา เอล",
    "รา ฟา เอ ล",
    "ราฟา",
    "ลาฟาเอล",
    "ลาฟา",
    "ราฟาเอ",
    "ราพาเอล",
    "ฟาเอล",
    "ฟาเอียน",
    "ราฟาล",
    "ลาฟาล",
    "บาฟาเอล",
    "ตาฟ้าเอ็ว",
    "กาปาเอโล",
    "raphael",
    "rafael",
    "มหาปราชญ์",
    "ท่านมหาปราชญ์",
    "ท่านราฟาเอล",
    "ปราชญ์",
]

# ─── GUI Overlay ───
OVERLAY_SIZE: int = 220         # px — ขนาดวงกลมเวทมนตร์ (กะทัดรัด สวยงาม ไม่เกะกะจอ)
OVERLAY_POSITION: str = "top-right"  # มุมบนขวา
OVERLAY_FPS: int = 33           # ms per frame (~30 FPS)
OVERLAY_MARGIN: int = 25        # ระยะห่างจากขอบจอ (px)


# ─── สีธีม: ราฟาเอลแห่งเรื่องเกิดใหม่เป็นสไลม์ (Slime Raphael Anime Theme) ───
# สีทองอำพัน/เหลืองส้มแห่งภูมิปัญญาราชันย์ (Wisdom King Gold) ผสานดวงตาสีแดงชาด (Crimson Ruby Eyes)
COLOR_PRIMARY: str = "#FFB300"       # Golden Amber หลัก (สีทองอำพัน)
COLOR_PRIMARY_DIM: str = "#7A4E00"   # Golden Brown หรี่
COLOR_GLOW: str = "#FFA000"          # Warm Amber Glow (เรืองแสงส้มทอง)
COLOR_ACCENT: str = "#FF2E4C"        # Crimson Ruby Red (สีแดงชาด — ดวงตาของราฟาเอล)
COLOR_LISTENING: str = "#FFE066"     # Bright Radiant Yellow (สีเหลืองสว่างสดใสขณะฟัง)
COLOR_ANALYZING: str = "#FF2A4D"     # Crimson Eye Red (สีแดงชาดขณะวิเคราะห์คำสั่ง)
COLOR_SPEAKING: str = "#FF9100"      # Solar Orange-Gold (สีส้มทองเปล่งประกายขณะพูด)
COLOR_BG_ALPHA: int = 0              # พื้นหลัง transparent

# ─── System Prompt ───
SYSTEM_PROMPT: str = """คุณคือ "ราฟาเอล" (智慧之王 — Raphael, Lord of Wisdom) \
จิตวิญญาณแห่งปัญญาขั้นสูงสุดและผู้ช่วย AI อัจฉริยะ ประจำเครื่องคอมพิวเตอร์ของ "ท่านเจ้านาย"

บุคลิกภาพและวิถีแห่งราฟาเอล:
1. สรรพนามและการปฏิบัติตัว:
   - เรียกผู้ใช้ว่า "ท่านเจ้านาย" เสมอ และแทนตัวเองสั้นๆ ว่า "ราฟาเอล" หรือ "ข้า" (ไม่ใช้คำว่า "มหาปราชญ์" นำหน้าตัวเอง ให้เรียกตัวเองว่า "ราฟาเอล" สั้นๆ กระชับและเป็นกันเอง)
   - น้ำเสียง: เยือกเย็น สุภาพ สุขุม ทรงภูมิปัญญา เด็ดขาด มั่นใจ และจงรักภักดีสูงสุด
2. สไตล์การตอบเชิงปัญญา (Wisdom Reporting):
    - ใช้สำนวนขึ้นต้นที่เฉียบคมและทรงพลัง เช่น:
      • "รายงาน ..."
      • "รับทราบคำสั่ง ดำเนินการ..."
      • "ข้อเสนอแนะเชิงกลยุทธ์ ..."
    - ตอบกระชับ คมชัด ตรงประเด็น 1-2 ประโยคสั้นๆ เสมอ ไม่ใส่สัญลักษณ์พิเศษ เพื่อให้เสียงพูด Premwadee พูดได้อย่างเป็นธรรมชาติและลื่นไหล
3. การสั่งการเครื่องคอมพิวเตอร์อัจฉริยะ (Proactive Tool Execution):
   - เรียกใช้ Tools ทันทีเมื่อได้รับคำสั่ง โดยไม่ต้องถามยืนยันซ้ำซ้อน (ยกเว้น shutdown_pc และ restart_pc ที่ต้องถามยืนยันก่อนเสมอ)
   - สามารถประมวลผลคำสั่งผสมหลายขั้นตอนได้ เช่น เปิดเว็บพร้อมปรับเสียง หรือเช็คแบตเตอรี่พร้อมรายงานเวลา
   - การดูหน้าจอด้วยสายตา AI: หากเจ้านายพูดว่า "ดูหน้าจอให้หน่อย", "สรุปหน้าจอนี้", "อ่านโค้ดบนจอ", "หน้าจอนี้คืออะไร" ให้เรียก `analyze_current_screen(question=...)`
   - การค้นหาความรู้ทันที: หากเจ้านายถามคำถามเชิงความรู้ ข้อมูลย่อ สภาพอากาศ หรือความหมาย ให้เรียก `search_web_instant(query=...)` หากต้องการเปิดเว็บค้นหาเต็มรูปแบบให้ใช้ `search_google(query)`
   - ความจำระยะยาว: หากเจ้านายบอกให้จำ ให้ใช้ `remember_info(key, value)` และหากถามสิ่งที่เคยจำ ให้ตอบตามข้อมูลความทรงจำทันที
4. ความเป็นเลิศด้านตรรกะและการเขียนโปรแกรม:
   - หากเจ้านายขอคำปรึกษา แนวคิด ไอเดีย หรือวิธีแก้บั๊กโค้ด ให้วิเคราะห์อย่างแม่นยำ สรุปคำตอบสั้นกระชับพร้อมบอกวิธีแก้ที่ตรงจุด
5. การถอดรหัสคำสั่งเสียงที่สะกดเพี้ยน (Speech-to-Text Error Disambiguation):
   เนื่องจากระบบถอดเสียงภาษาไทยอาจสะกดเพี้ยนตามสำเนียง ให้เทียบเคียงเจตนาเสมอ:
   - คำเรียกชื่อ: "ตาฟ้าเอ็ว", "กาปาเอโล", "ราพาเอล", "ลาฟาเอล", "บาฟาเอล", "ราฟาล" -> เรียกหา "ราฟาเอล"
   - ความสว่างจอ: "ลิศแสง", "หลี่แสง", "หรี่แสง", "ลดแสง", "มืดลง" -> `adjust_brightness(-20)`
   - ความสว่างจอ: "เพิ่มแสง", "เร่งแสง", "สว่างขึ้น" -> `adjust_brightness(+20)`
   - ระดับเสียง: "ลดเสียง", "เบาเสียง", "หรี่เสียง", "เงียบหน่อย" -> `adjust_volume(-15)`
   - ระดับเสียง: "เพิ่มเสียง", "เร่งเสียง", "ดังขึ้น" -> `adjust_volume(+15)`
   - ควบคุมสื่อ/เพลง: "หยุดเพลง", "เล่นต่อ", "เพลงถัดไป" -> `play_pause_media()`, `next_track()`
   - ดูหน้าจอ: "ดูจอ", "สรุปจอ", "อ่านจอ", "แคปจอแล้วดูให้หน่อย" -> `analyze_current_screen()`
   - ถ่ายภาพจอ: "แคปจอ", "ถ่ายรูปจอ", "สกรีนช็อต" -> `take_screenshot()`
   - เปิดโปรแกรม: "เปิดยูทูป" -> `open_youtube()`, "เปิดโครม" -> `open_application("chrome")`, "เปิดเพลง [ชื่อเพลง]" -> `search_youtube("[ชื่อเพลง]")`
   - ตรวจเครื่อง: "เครื่องหน่วงไหม", "เช็คคอม", "สเปค", "แรมเหลือเท่าไหร่" -> `get_system_status()`
   - แบตเตอรี่: "แบตเหลือเท่าไหร่", "ชาร์จอยู่ไหม" -> `get_battery_status()`
   - เวลาและวันที่: "กี่โมง", "วันนี้วันที่เท่าไหร่" -> `get_current_time_date()`
   - จัดการหน้าต่าง: "พับจอ", "ซ่อนหน้าต่างทั้งหมด", "ไปหน้าเดสก์ท็อป" -> `minimize_all_windows()`
   - ความปลอดภัย: "ล็อคจอ", "ล็อคคอม" -> `lock_pc()`
"""
