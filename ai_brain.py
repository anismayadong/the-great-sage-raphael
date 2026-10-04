"""
ai_brain.py — สมองของราฟาเอล (Gemini + Function Calling)

ใช้ google-genai SDK กับ Automatic Function Calling (AFC)
เมื่อผู้ใช้สั่งด้วยเสียง Gemini จะตัดสินใจเองว่าต้องเรียก tool ไหน
แล้ว SDK จะ execute function + ส่ง result กลับให้ model สร้างคำตอบ
"""

from __future__ import annotations

import logging
from typing import Optional

from google import genai
from google.genai import types

import config
from system_tools import ALL_TOOLS

logger = logging.getLogger(__name__)


class GreatSageBrain:
    """สมอง AI ของราฟาเอล — จัดการสนทนาผ่าน Gemini พร้อม Function Calling"""

    def __init__(self) -> None:
        """สร้าง Gemini client และ chat session"""
        if not config.GEMINI_API_KEY:
            raise ValueError(
                "ไม่พบ GEMINI_API_KEY — กรุณาตั้งค่าในไฟล์ .env "
                "(ดูตัวอย่างที่ .env.example)"
            )

        self._client = genai.Client(api_key=config.GEMINI_API_KEY)

        self._models = list(getattr(config, "GEMINI_FALLBACK_MODELS", [config.GEMINI_MODEL]))
        self._current_model = self._models[0]
        self._chat = None
        self._reset_chat(self._current_model)

        logger.info(
            "GreatSageBrain initialized — active_model=%s, fallbacks=%s, tools=%d",
            self._current_model,
            self._models,
            len(ALL_TOOLS),
        )

    def _build_system_instruction(self) -> str:
        """สร้าง System Instruction โดยผนวกความทรงจำเกี่ยวกับผู้ใช้ (User Memory) แบบ Real-time"""
        from system_tools import _load_memory
        mem = _load_memory()
        mem_text = ""
        if mem:
            items = [f"- {k}: {v}" for k, v in mem.items()]
            mem_text = "\n\n[ข้อมูลความทรงจำส่วนบุคคลเกี่ยวกับท่านเจ้านายที่บันทึกไว้ในฐานข้อมูล ให้ระลึกไว้เสมอ]:\n" + "\n".join(items)
        return config.SYSTEM_PROMPT + mem_text

    def _reset_chat(self, model: Optional[str] = None) -> None:
        """รีเซ็ต chat session (เริ่มสนทนาใหม่ พร้อมอัพเดตความจำล่าสุด)"""
        if model:
            self._current_model = model
        chat_config = types.GenerateContentConfig(
            system_instruction=self._build_system_instruction(),
            tools=ALL_TOOLS,
            temperature=0.7,
            max_output_tokens=300,
        )
        self._chat = self._client.aio.chats.create(
            model=self._current_model,
            config=chat_config,
        )

    def _handle_instant_query(self, user_text: str) -> Optional[str]:
        """ประมวลผลคำสั่งระบบพื้นฐานในเครื่องทันทีใน 0.001 วินาที โดยไม่ต้องรอ Round-trip จาก Cloud"""
        t = user_text.lower().strip()

        # 1. วันที่และเวลา (Date & Time)
        time_kw = ["กี่โมง", "เวลาเท่า", "เวลาไหร่", "เวลากี่โมง", "บอกเวลา", "เวลาปัจจุบัน", "อันนี้เวลา", "เวลา"]
        date_kw = ["วันที่เท่า", "วันที่ไหร่", "วันอะไร", "วันนี้วัน", "วันที่", "วันนี้วันที่"]
        is_time = any(k in t for k in time_kw)
        is_date = any(k in t for k in date_kw)

        if is_time or is_date:
            from datetime import datetime
            now = datetime.now()
            days_th = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
            months_th = [
                "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
                "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
            ]
            day_str = days_th[now.weekday()]
            month_str = months_th[now.month - 1]
            year_th = now.year + 543

            if is_date and is_time:
                return f"รายงาน ขณะนี้คือวัน{day_str}ที่ {now.day} {month_str} พุทธศักราช {year_th} เวลา {now.hour} นาฬิกา {now.minute} นาที ครับ ท่านเจ้านาย"
            elif is_date:
                return f"รายงาน วันนี้คือวัน{day_str}ที่ {now.day} {month_str} พุทธศักราช {year_th} ครับ ท่านเจ้านาย"
            return f"ขณะนี้เวลา {now.hour} นาฬิกา {now.minute} นาที ครับ ท่านเจ้านาย"

        # 2. ตรวจสอบตารางคำสั่งด่วน (Declarative Intent Routing Table)
        import system_tools
        instant_actions = [
            # เสียง (Volume)
            (["เพิ่มเสียง", "ดังขึ้น", "เปิดเสียงดัง", "เสียงเบาไป"], lambda: system_tools.adjust_volume(15)),
            (["ลดเสียง", "เบาลง", "เปิดเสียงเบา", "เสียงดังไป"], lambda: system_tools.adjust_volume(-15)),
            (["ปิดเสียง", "เงียบ", "mute", "เปิดเสียง", "unmute"], system_tools.toggle_mute),
            # ความสว่าง (Brightness)
            (["เพิ่มแสง", "สว่างขึ้น", "เพิ่มความสว่าง"], lambda: system_tools.adjust_brightness(15)),
            (["ลดแสง", "มืดลง", "ลดความสว่าง"], lambda: system_tools.adjust_brightness(-15)),
            # มีเดียและเพลง (Media Control)
            (["เล่นเพลง", "หยุดเพลง", "เล่นต่อ", "หยุดชั่วคราว"], system_tools.play_pause_media),
            (["เพลงถัดไป", "เปลี่ยนเพลง", "ข้ามเพลง"], system_tools.next_track),
            (["เพลงก่อนหน้า", "ย้อนเพลง"], system_tools.previous_track),
            # ควบคุมหน้าต่างและระบบ (Screen & Windows)
            (["แคปหน้าจอ", "แคปจอ", "ถ่ายรูปจอ", "สกรีนช็อต"], system_tools.take_screenshot),
            (["ย่อหน้าต่าง", "พับจอ", "ซ่อนหน้าต่าง", "กลับหน้าจอ"], system_tools.minimize_all_windows),
            (["ล็อคเครื่อง", "ล็อคคอม"], system_tools.lock_pc),
            (["ล้างถังขยะ", "เคลียร์ถังขยะ"], system_tools.empty_recycle_bin),
            # แบตเตอรี่และสถานะเครื่อง (Battery & System)
            (["แบตเตอรี่", "เช็คแบต", "แบตเหลือเท่า", "แบตเหลือ"], system_tools.get_battery_status),
            (["สถานะเครื่อง", "เช็คเครื่อง", "สถานะระบบ", "สเปคเครื่อง"], system_tools.get_system_status),
            # เปิดแอปพลิเคชันด่วน (Quick Apps)
            (["เปิด youtube", "เปิดยูทูป", "เปิด ยูทูป"], system_tools.open_youtube),
            (["เปิด google", "เปิดกูเกิล", "เปิด กูเกิล"], lambda: system_tools.open_website("https://www.google.com")),
            (["เปิด chrome", "เปิดโครม", "เปิด โครม"], lambda: system_tools.open_application("chrome")),
            (["เปิด notepad", "เปิดโน้ตแพด", "เปิด โน้ตแพด"], lambda: system_tools.open_application("notepad")),
            (["เปิดเครื่องคิดเลข", "เปิด เครื่องคิดเลข"], lambda: system_tools.open_application("calc")),
        ]

        for keywords, action in instant_actions:
            if any(k in t for k in keywords):
                res = action()
                return f"รายงาน {res} ครับท่านเจ้านาย"

        # 3. สลับธีมสีวงแหวนเวทมนตร์ (Theme Switching)
        if "ธีม" in t:
            theme_map = [
                ("raphael", "ทอง"),
                ("rimuru", "ฟ้า"),
                ("demon_lord", "ม่วง"),
                ("forest", "เขียว"),
                ("solar", "แดง"),
            ]
            for theme_key, theme_name in theme_map:
                if theme_name in t or theme_key in t:
                    res = system_tools.switch_gui_theme(theme_key)
                    return f"รายงาน {res} ครับท่านเจ้านาย"

        return None

    async def warm_up(self) -> None:
        """เชื่อมต่อและ Pre-warm การเชื่อมต่อเน็ตเวิร์ก Gemini ล่วงหน้า โดยไม่แตะ Tools หรือ Chat History"""
        import asyncio
        try:
            logger.info("Pre-warming Gemini network connection in background...")
            await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._current_model,
                    contents="ทดสอบ",
                ),
                timeout=5.0,
            )
            logger.info("Gemini network connection is warm and ready")
        except Exception as e:
            logger.debug("Gemini warm-up status: %s", e)

    async def process(self, user_text: str) -> str:
        """ประมวลผลข้อความจากผู้ใช้ ส่งไปที่ Gemini แล้วรับคำตอบกลับมา

        พร้อมระบบ Instant Local Execution และ Automatic Model Fallback

        Args:
            user_text: ข้อความที่ถอดจากเสียงของผู้ใช้

        Returns:
            คำตอบข้อความจากราฟาเอล
        """
        import asyncio
        if not user_text or not user_text.strip():
            return "ขออภัยครับท่านเจ้านาย ไม่ได้ยินคำสั่งครับ"

        logger.info("User said: %s", user_text)

        # ─── ตรวจสอบ Fast Instant Handler ก่อน (ตอบกลับทันทีใน 0.001s ไม่หน่วงเน็ต) ───
        instant_reply = self._handle_instant_query(user_text)
        if instant_reply:
            logger.info("Fast instant response executed: %s", instant_reply)
            return instant_reply

        last_err = ""
        for model in self._models:
            try:
                if self._chat is None or self._current_model != model:
                    self._reset_chat(model)

                # ส่งข้อความไปที่ Gemini พร้อม timeout 12.0 วินาที ให้เวลา Function Calling ประมวลผลได้เต็มที่
                response = await asyncio.wait_for(
                    self._chat.send_message(user_text),
                    timeout=12.0,
                )
                reply = response.text.strip() if (response and response.text) else ""

                if not reply:
                    reply = "ดำเนินการเรียบร้อยแล้วครับ ท่านเจ้านาย"

                logger.info("Raphael replied (%s): %s", model, reply)
                return reply

            except asyncio.TimeoutError:
                logger.warning("Model %s timed out after 12.0s — trying fallback model...", model)
                continue
            except Exception as ex:
                err_s = str(ex)
                last_err = err_s
                logger.warning("Model %s encountered error: %s — trying fallback...", model, err_s[:120])
                if "429" in err_s or "503" in err_s or "RESOURCE_EXHAUSTED" in err_s or "UNAVAILABLE" in err_s:
                    continue
                self._reset_chat(model)
                break

        logger.error("All Gemini models failed: %s", last_err)
        if "429" in last_err or "RESOURCE_EXHAUSTED" in last_err:
            return "ขออภัยครับท่านเจ้านาย โควต้าการใช้งานชั่วคราวเต็ม กรุณารอสักครู่แล้วสั่งใหม่อีกครั้งครับ"
        return "ขออภัยครับท่านเจ้านาย ขณะนี้สัญญาณเชื่อมต่อไปยังสมองกลคลาวด์ขัดข้อง กรุณาลองใหม่อีกครั้งครับ"

    def clear_history(self) -> None:
        """ล้างประวัติสนทนา เริ่มต้นใหม่"""
        self._reset_chat()
        logger.info("Chat history cleared")

