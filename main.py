"""
main.py — จุดเริ่มต้นของ Great Sage Raphael

ร้อยเรียง GUI overlay, voice engine, AI brain เข้าด้วยกัน
ใช้ qasync เพื่อ bridge asyncio event loop กับ Qt event loop

Flow หลัก:
1. แสดง overlay (IDLE) + เริ่ม continuous listening
2. ฟังเสียงต่อเนื่อง → ถอดเป็นข้อความ → ตรวจจับ wake word "ราฟาเอล"
3. เมื่อพบ wake word → state LISTENING → บันทึกคำสั่ง
4. state ANALYZING → ส่งไป Gemini (อาจเรียก tools)
5. state SPEAKING → เล่นเสียงตอบกลับ
6. กลับ IDLE → วนลูปฟังต่อ
"""

from __future__ import annotations

import asyncio
import logging
import sys
import os

# ─── Setup logging ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-14s] %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def _setup_windows_environment() -> None:
    """ตั้งค่า CUDA DLL path และเชื่อมต่อไปยัง Default desktop ของ Windows"""
    if sys.platform != "win32":
        return

    # 1. เชื่อมต่อไปยัง Default interactive desktop (กรณีรันจาก agent/service runner)
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hdesk = user32.OpenDesktopW("Default", 0, False, 0x10000000)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
            logger.info("Attached thread to interactive Default desktop")
    except Exception as e:
        logger.warning("Could not attach to Default desktop: %s", e)

    # 2. ตั้งค่า DLL search path สำหรับ NVIDIA CUDA/CUDNN
    from pathlib import Path
    _venv_prefix = Path(sys.prefix)
    for _d in _venv_prefix.glob("Lib/site-packages/nvidia/*/bin"):
        if _d.is_dir():
            try:
                os.add_dll_directory(str(_d))
            except Exception:
                pass
            os.environ["PATH"] = str(_d) + os.pathsep + os.environ.get("PATH", "")


def main() -> None:
    """Entry point — สร้าง Qt app + asyncio event loop + เริ่มทำงาน"""

    # เตรียม environment สำหรับ Windows ก่อนสร้าง GUI
    _setup_windows_environment()

    # ─── Import dependencies ───
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    import qasync

    from gui_overlay import MagicCircleOverlay, AssistantState
    from voice_engine import SpeechRecognizer, TextToSpeech
    from ai_brain import GreatSageBrain
    from system_tools import register_theme_callback
    import config

    # ─── สร้าง Qt Application ───
    app = QApplication(sys.argv)
    app.setApplicationName("Great Sage Raphael")
    app.setQuitOnLastWindowClosed(False)

    # ─── สร้าง asyncio event loop ผ่าน qasync ───
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # ─── สร้าง Components ───
    logger.info("═══ Great Sage Raphael — Initializing ═══")

    overlay = MagicCircleOverlay()
    overlay.show()
    register_theme_callback(overlay.set_theme)
    logger.info("Overlay displayed & theme callback registered")

    # โหลด STT model (อาจใช้เวลาครั้งแรก)
    overlay.set_state(AssistantState.ANALYZING)
    app.processEvents()  # อัพเดต GUI ก่อนโหลด model

    stt = SpeechRecognizer()
    tts = TextToSpeech(on_amplitude=overlay.set_speaking_amplitude)
    brain = GreatSageBrain()

    overlay.set_state(AssistantState.IDLE)

    logger.info("═══ All components loaded — Starting ═══")

    # ─── State ───
    is_processing = False
    manual_trigger_event = asyncio.Event()

    # ─── Async main loop ───

    async def process_command(command_text: str) -> None:
        """ประมวลผลคำสั่ง: Instant Routing / Gemini Cloud → TTS แบบ Queue พร้อม Animation"""
        nonlocal is_processing

        is_processing = True
        try:
            # ─── ANALYZING ───
            overlay.set_state(AssistantState.ANALYZING)

            response = await brain.process(command_text)

            # ─── SPEAKING (ส่งเข้า Queue + เริ่มพูดทันที ไม่บล็อกลูป) ───
            overlay.set_state(AssistantState.SPEAKING)
            tts.enqueue(response)

            # เฝ้าดูจนกว่าจะพูดจบทุกช่วง จึงปรับ overlay กลับเป็น IDLE
            async def _watch_speech_done() -> None:
                await tts.wait_until_done()
                if not is_processing and not manual_trigger_event.is_set():
                    overlay.set_state(AssistantState.IDLE)

            asyncio.create_task(_watch_speech_done())

        except Exception as e:
            logger.error("Error processing command: %s", e, exc_info=True)
            overlay.set_state(AssistantState.SPEAKING)
            tts.enqueue("ขออภัยครับท่านเจ้านาย เกิดข้อผิดพลาด")
            async def _watch_err_done() -> None:
                await tts.wait_until_done()
                if not is_processing and not manual_trigger_event.is_set():
                    overlay.set_state(AssistantState.IDLE)

            asyncio.create_task(_watch_err_done())

        finally:
            is_processing = False

    async def unified_listening_loop() -> None:
        """ลูปดักจับเสียงหลัก (Single Unified Audio Pipeline)

        ควบคุมการเข้าถึงไมโครโฟนเพียงจุดเดียว ทั้งการฟัง Wake Word
        และการคลิกวงแหวน เพื่อกำจัดปัญหาแย่งพอร์ตไมค์ (Race Condition) 100%
        """
        nonlocal is_processing

        # เริ่มต้น Pre-warm โมเดล Gemini ล่วงหน้าในพื้นหลัง (ตัดอาการ Cold Start 100%)
        asyncio.create_task(brain.warm_up())

        # พูดทักทายครั้งแรก
        overlay.set_state(AssistantState.SPEAKING)
        tts.enqueue("ราฟาเอลพร้อมทำงานแล้วครับ ท่านเจ้านาย")
        await tts.wait_until_done()
        overlay.set_state(AssistantState.IDLE)

        while True:
            try:
                # ถ้ากำลังประมวลผลคำสั่ง (คิด/ค้นหา) ให้รอ แต่ถ้าแค่กำลังพูด (is_speaking) สามารถฟังต่อเพื่อ barge-in ได้
                if is_processing:
                    await asyncio.sleep(0.1)
                    continue

                # ─── กรณีที่ 1: ผู้ใช้คลิกที่วงแหวนเวทมนตร์ (Direct Command) ───
                if manual_trigger_event.is_set():
                    manual_trigger_event.clear()
                    stt.reset_abort()
                    is_processing = True
                    overlay.set_state(AssistantState.LISTENING)
                    logger.info("Manual click trigger: Listening directly for command...")

                    # บันทึกเสียงคำสั่งของผู้ใช้โดยตรงจนกว่าจะพูดจบ
                    cmd_audio = await asyncio.get_event_loop().run_in_executor(
                        None, stt.record_until_silence
                    )
                    overlay.set_state(AssistantState.ANALYZING)
                    cmd_text = await asyncio.get_event_loop().run_in_executor(
                        None, stt.transcribe, cmd_audio
                    )

                    if cmd_text.strip():
                        # ไม่ต้องมี Wake Word! คำสั่งใดๆ ที่พูดหลังคลิกจะส่งไปทำงานทันที
                        logger.info("Executing clicked command: '%s'", cmd_text)
                        await process_command(cmd_text)
                    else:
                        overlay.set_state(AssistantState.SPEAKING)
                        tts.enqueue("ไม่ได้ยินคำสั่งครับ ท่านเจ้านาย")
                        await tts.wait_until_done()
                        overlay.set_state(AssistantState.IDLE)
                        is_processing = False
                    continue

                # ─── กรณีที่ 2: โหมดฟังเสียงพื้นหลัง (ตรวจจับ Wake Word "ราฟาเอล") ───
                audio = await asyncio.get_event_loop().run_in_executor(
                    None, stt.record_audio, config.RECORD_CHUNK_SEC
                )

                # หากมีผู้ใช้คลิกระหว่างกำลังบันทึก chunk ให้ข้ามไปโหมดรับคำสั่งทันที
                if manual_trigger_event.is_set():
                    continue

                text = await asyncio.get_event_loop().run_in_executor(
                    None, stt.transcribe, audio
                )

                if not text.strip():
                    continue

                # ตรวจจับ Wake Word
                found, command = stt.detect_wake_word(text)

                if not found:
                    logger.debug("No wake word in: '%s'", text[:50])
                    continue

                logger.info("Wake word detected! Command: '%s'", command)

                # ─── Barge-in: ถ้ากำลังพูดอยู่ ให้หยุดทันที ───
                if getattr(tts, "is_speaking", False):
                    logger.info("Wake word during speech -> Barge-in stop")
                    tts.stop()

                is_processing = True

                if command.strip():
                    # พูดคำสั่งต่อท้ายชื่อ เช่น "ราฟาเอล เปิดยูทูป" → ทำงานทันที
                    await process_command(command)
                else:
                    # พูดแค่เรียกชื่อ "ราฟาเอล" → ตอบรับแล้วรอฟังคำสั่งต่อ
                    overlay.set_state(AssistantState.SPEAKING)
                    tts.enqueue("ครับ ท่านเจ้านาย")
                    await tts.wait_until_done()
                    overlay.set_state(AssistantState.LISTENING)
                    stt.reset_abort()

                    cmd_audio = await asyncio.get_event_loop().run_in_executor(
                        None, stt.record_until_silence
                    )
                    overlay.set_state(AssistantState.ANALYZING)
                    cmd_text = await asyncio.get_event_loop().run_in_executor(
                        None, stt.transcribe, cmd_audio
                    )

                    if cmd_text.strip():
                        await process_command(cmd_text)
                    else:
                        overlay.set_state(AssistantState.SPEAKING)
                        tts.enqueue("ไม่ได้ยินคำสั่งครับ ท่านเจ้านาย")
                        await tts.wait_until_done()
                        overlay.set_state(AssistantState.IDLE)
                        is_processing = False

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Listening loop error: %s", e, exc_info=True)
                is_processing = False
                await asyncio.sleep(0.5)

    def on_overlay_clicked() -> None:
        """เมื่อคลิกที่ overlay → ตอบสนองทันทีแบบ 0ms และสลับเข้าโหมดรับคำสั่ง (รองรับ Barge-in)"""
        # Barge-in: ถ้ากำลังพูดอยู่ หยุดเสียงทันที
        if getattr(tts, "is_speaking", False):
            logger.info("Overlay clicked during speech -> Barge-in stop")
            tts.stop()

        overlay.set_state(AssistantState.LISTENING)
        stt.abort_recording()
        manual_trigger_event.set()

    # ─── Connect signals ───
    overlay.clicked.connect(on_overlay_clicked)
    overlay.state_label_text.connect(
        lambda msg: brain.clear_history() if msg == "clear_chat" else None
    )

    # ─── เริ่มลูปหลัก ───
    with loop:
        main_task = loop.create_task(unified_listening_loop())
        try:
            loop.run_forever()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            if not main_task.done():
                main_task.cancel()
            try:
                loop.run_until_complete(asyncio.gather(main_task, return_exceptions=True))
            except Exception:
                pass


if __name__ == "__main__":
    main()
