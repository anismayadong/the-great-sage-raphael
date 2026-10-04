"""
voice_engine.py — ระบบเสียงของราฟาเอล (STT + TTS + Wake Word)

- STT: faster-whisper (medium model, CUDA, float16) — แปลงเสียงเป็นข้อความ
- TTS: edge-tts (th-TH-PremwadeeNeural) — แปลงข้อความเป็นเสียง
- Wake Word: ตรวจจับคำว่า "ราฟาเอล" จาก transcription ก่อนส่งไป AI brain
"""

from __future__ import annotations

import asyncio
import logging

import os
import re
import time
import threading
from pathlib import Path
from typing import Optional, Callable


import numpy as np
import sounddevice as sd
import soundfile as sf
import edge_tts

import config

# ตั้งค่า DLL search path สำหรับ NVIDIA CUDA/CUDNN ใน venv อัตโนมัติ
def _setup_nvidia_dlls() -> None:
    import sys
    from pathlib import Path
    if sys.platform != "win32":
        return
    _venv_prefix = Path(sys.prefix)
    for _d in _venv_prefix.glob("Lib/site-packages/nvidia/*/bin"):
        if _d.is_dir():
            try:
                os.add_dll_directory(str(_d))
            except Exception:
                pass
            os.environ["PATH"] = str(_d) + os.pathsep + os.environ.get("PATH", "")

_setup_nvidia_dlls()

logger = logging.getLogger(__name__)


# Mutex ป้องกันการเข้าถึง Microphone พร้อมกันข้ามเธรด (ป้องกันพอร์ต Audio ชนกัน / ค่า NaN)
_mic_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════
#  STT — Speech-to-Text (faster-whisper)
# ═══════════════════════════════════════════════════════════

class SpeechRecognizer:
    """ถอดเสียงภาษาไทยด้วย faster-whisper (local, GPU-accelerated) ค่าเริ่มต้นมาตรฐาน"""

    def __init__(self) -> None:
        """โหลด Whisper model และค้นหาไมโครโฟนที่เหมาะสม"""
        logger.info(
            "Loading Whisper model=%s device=%s compute=%s ...",
            config.WHISPER_MODEL_SIZE,
            config.WHISPER_DEVICE,
            config.WHISPER_COMPUTE_TYPE,
        )
        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            config.WHISPER_MODEL_SIZE,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
        )
        logger.info("Whisper model loaded successfully")

        self._abort_flag = threading.Event()
        self._device_index = self._find_working_input_device()
        logger.info("Selected audio input device index: %s", self._device_index)

    def _find_working_input_device(self) -> Optional[int]:
        """ค้นหาไมโครโฟนตามการตั้งค่า (ค่าเริ่มต้น: 'default' / ไมโครโฟนของระบบ)"""
        dev_setting = getattr(config, "INPUT_DEVICE", "default")
        cfg_index = getattr(config, "INPUT_DEVICE_INDEX", None)

        # 1. ถ้าระบุ index เป็นตัวเลขโดยตรง
        target_index = cfg_index if cfg_index is not None else (dev_setting if isinstance(dev_setting, int) else None)
        if target_index is not None:
            try:
                rec = sd.rec(int(0.05 * config.SAMPLE_RATE), samplerate=config.SAMPLE_RATE, channels=1, device=target_index, dtype="float32")
                sd.wait()
                logger.info("Configured audio input device [%s] verified successfully", target_index)
                return target_index
            except Exception as e:
                logger.warning("Configured device [%s] failed test: %s", target_index, e)

        # 2. โหมด 'default': ทดสอบใช้ System Default Device (device=None) โดยตรง
        if dev_setting == "default" or target_index is None:
            try:
                rec = sd.rec(int(0.05 * config.SAMPLE_RATE), samplerate=config.SAMPLE_RATE, channels=1, device=None, dtype="float32")
                sd.wait()
                flat = rec.flatten()
                peak = float(np.max(np.abs(flat))) if len(flat) > 0 else 0.0
                if not (np.isnan(flat).any() or np.isinf(flat).any()) and peak < 2.0:
                    logger.info("Using system default microphone (device=None) directly")
                    return None
            except Exception as e:
                logger.debug("System default (device=None) encountered host error: %s. Resolving hardware endpoint...", e)

        # 3. ค้นหาอุปกรณ์ไมโครโฟนที่เป็นโหมดแชร์ (Shared Mode เท่านั้น: WASAPI / DirectSound / MME)
        # ห้ามใช้ WDM-KS เด็ดขาด เพราะ WDM-KS เป็น Kernel Exclusive Lock ที่จะแย่งไมค์คนเดียวจน Discord เกิด Error 3002
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
        safe_candidates = []

        for idx, dev in enumerate(devices):
            if dev["max_input_channels"] <= 0:
                continue
            api_name = hostapis[dev["hostapi"]]["name"]
            dev_name = dev["name"]

            # กรองตัด WDM-KS ออก 100% เพื่อป้องกันปัญหาแย่งพอร์ตไมค์กับ Discord และแอปอื่นๆ
            if "wdm-ks" in api_name.lower():
                continue

            # เรียงลำดับความปลอดภัย: DirectSound / MME / WASAPI Shared
            if "directsound" in api_name.lower():
                safe_candidates.insert(0, idx)
            elif "mme" in api_name.lower():
                safe_candidates.append(idx)
            else:
                safe_candidates.append(idx)

        # ทดสอบหาอุปกรณ์ในกลุ่ม Shared ที่พร้อมทำงาน
        for idx in safe_candidates:
            dev = devices[idx]
            api_name = hostapis[dev["hostapi"]]["name"]
            try:
                rec = sd.rec(int(0.05 * config.SAMPLE_RATE), samplerate=config.SAMPLE_RATE, channels=1, device=idx, dtype="float32")
                sd.wait()
                flat = rec.flatten()
                peak = float(np.max(np.abs(flat))) if len(flat) > 0 else 0.0
                if peak > 2.0 or np.isnan(flat).any() or np.isinf(flat).any():
                    continue
                logger.info("Shared microphone endpoint selected: [%d] %s (%s)", idx, dev["name"], api_name)
                return idx
            except Exception:
                continue

        default_dev = sd.default.device[0]
        logger.info("Using system default microphone index: %s (Shared Mode)", default_dev)
        return default_dev if default_dev >= 0 else None

    def abort_recording(self) -> None:
        """ยกเลิกการบันทึกเสียงแบบ cooperative (ไม่ทำลายพอร์ต audio / ป้องกัน PortAudio crash)"""
        self._abort_flag.set()

    def reset_abort(self) -> None:
        """รีเซ็ตสัญญาณยกเลิกการบันทึก"""
        self._abort_flag.clear()

    def record_audio(self, duration: float = config.RECORD_CHUNK_SEC, block_sec: float = 0.2) -> np.ndarray:
        """บันทึกเสียงดิบผ่าน continuous InputStream บล็อกละ 0.2s
        ตัดปัญหาเสียงกระตุก/ช่องว่างเสียง (zero drops) และตอบสนองต่อการ abort ได้ทันทีใน 0.2s

        Args:
            duration: ระยะเวลารวมที่ต้องการบันทึก (วินาที)
            block_sec: ความยาวแต่ละบล็อกในการอ่านข้อมูล

        Returns:
            Audio data เป็น numpy array (float32, mono, 16kHz)
        """
        block_samples = int(block_sec * config.SAMPLE_RATE)
        total_samples = int(duration * config.SAMPLE_RATE)
        chunks: list[np.ndarray] = []
        read_samples = 0

        with _mic_lock:
            self._abort_flag.clear()
            try:
                with sd.InputStream(
                    samplerate=config.SAMPLE_RATE,
                    channels=config.CHANNELS,
                    device=self._device_index,
                    dtype="float32",
                    blocksize=block_samples,
                ) as stream:
                    while read_samples < total_samples:
                        if self._abort_flag.is_set():
                            logger.debug("record_audio interrupted cooperatively at %.2fs", read_samples / config.SAMPLE_RATE)
                            break
                        cur_samples = min(block_samples, total_samples - read_samples)
                        data, overflowed = stream.read(cur_samples)
                        flat = data.flatten()
                        if not (np.isnan(flat).any() or np.isinf(flat).any()):
                            chunks.append(flat)
                        read_samples += cur_samples
            except Exception as e:
                logger.warning("Continuous stream recording error: %s (device=%s)", e, self._device_index)
                self._device_index = self._find_working_input_device()

        if not chunks:
            return np.array([], dtype=np.float32)
        return np.concatenate(chunks)

    def record_until_silence(
        self,
        duration: Optional[float] = None,
        silence_timeout: Optional[float] = None,
    ) -> np.ndarray:
        """บันทึกเสียงคำสั่งต่อเนื่องด้วย InputStream พร้อม Smart VAD ตรวจจับการหยุดพูดแบบ real-time
        หยุดทันทีเมื่อผู้ใช้พูดจบ ให้ความลื่นไหลสูงสุด และประหยัดเวลา

        Args:
            duration: ระยะเวลาบันทึกสูงสุด (วินาที)
            silence_timeout: ระยะเวลาเงียบหลังจากเริ่มพูดเพื่อตัดจบ (วินาที)

        Returns:
            Audio data เป็น numpy array (float32, mono, 16kHz)
        """
        max_duration = duration or getattr(config, "VAD_MAX_RECORD_SEC", 4.5)
        timeout = silence_timeout or getattr(config, "VAD_SILENCE_TIMEOUT", 0.65)
        min_speech_sec = 0.35
        block_sec = 0.15
        block_samples = int(block_sec * config.SAMPLE_RATE)
        max_samples = int(max_duration * config.SAMPLE_RATE)

        chunks: list[np.ndarray] = []
        read_samples = 0
        speech_started = False
        silence_elapsed = 0.0

        with _mic_lock:
            self._abort_flag.clear()
            try:
                with sd.InputStream(
                    samplerate=config.SAMPLE_RATE,
                    channels=config.CHANNELS,
                    device=self._device_index,
                    dtype="float32",
                    blocksize=block_samples,
                ) as stream:
                    while read_samples < max_samples:
                        if self._abort_flag.is_set():
                            break

                        data, _ = stream.read(block_samples)
                        flat = data.flatten()
                        if np.isnan(flat).any() or np.isinf(flat).any():
                            continue

                        chunks.append(flat)
                        read_samples += block_samples
                        elapsed = read_samples / config.SAMPLE_RATE

                        peak = float(np.max(np.abs(flat))) if len(flat) > 0 else 0.0
                        if 0.007 <= peak <= 2.0:
                            speech_started = True
                            silence_elapsed = 0.0
                        elif speech_started:
                            silence_elapsed += block_sec
                            if silence_elapsed >= timeout and elapsed >= min_speech_sec:
                                logger.debug("VAD detected end of speech at %.2fs", elapsed)
                                break
            except Exception as e:
                logger.warning("record_until_silence stream error: %s", e)
                self._device_index = self._find_working_input_device()

        if not chunks:
            return np.array([], dtype=np.float32)
        return np.concatenate(chunks)

    def transcribe(self, audio: np.ndarray) -> str:
        """แปลงเสียงเป็นข้อความภาษาไทยด้วย faster-whisper พร้อมระบบกรองเสียงเงียบและคำหลอน 100%

        Args:
            audio: Audio data (float32, mono, 16kHz)

        Returns:
            ข้อความที่ถอดได้
        """
        if len(audio) == 0:
            return ""

        # ป้องกัน audio สั้นเกินไป (< 0.3 วินาที)
        if len(audio) < int(config.SAMPLE_RATE * 0.30):
            return ""

        # ตรวจสอบความถูกต้องของสัญญาณเสียง ป้องกัน NaN / Inf หรือค่าผิดเพี้ยนจากฮาร์ดแวร์
        if np.isnan(audio).any() or np.isinf(audio).any():
            logger.warning("Corrupt audio buffer (contains NaN/Inf), skipping transcription")
            return ""

        # คำนวณระดับพลังงานเสียงสูงสุด (Peak)
        peak = float(np.max(np.abs(audio))) if len(audio) > 0 else 0.0

        if peak > 2.0 or np.isnan(peak) or np.isinf(peak):
            logger.warning("Corrupt audio buffer (peak=%.4f), skipping transcription", peak)
            return ""

        # ถ้าเสียงเบาต่ำกว่า 0.0035 (เงียบสนิท ไม่มีสัญญาณเสียง) ตัดทิ้งทันที
        # ป้องกัน Whisper นำเสียงเงียบไปเดาเป็นคำหลอน และประหยัดเวลา GPU
        if peak < 0.0035:
            logger.debug("Ambient silence detected (peak=%.4f), skipping transcription", peak)
            return ""

        # ปรับระดับเสียงแบบจำกัด Gain (ไม่เกิน 10.0x) เพื่อดึงเสียงพูดให้ชัดเจนสำหรับ Whisper
        gain = min(10.0, 0.40 / (peak + 1e-7))
        audio = audio * gain

        logger.debug("Transcribing audio (%d samples, peak=%.4f, gain=%.2f)...", len(audio), peak, gain)
        start = time.time()

        try:
            vad_filter = getattr(config, "WHISPER_VAD_FILTER", True)
            initial_prompt = getattr(config, "WHISPER_INITIAL_PROMPT", "") or None
            beam_size = getattr(config, "WHISPER_BEAM_SIZE", 1)

            segments, info = self._model.transcribe(
                audio,
                language=config.WHISPER_LANGUAGE,
                initial_prompt=initial_prompt,
                beam_size=beam_size,
                condition_on_previous_text=False,
                vad_filter=vad_filter,
                vad_parameters=dict(min_silence_duration_ms=350, speech_pad_ms=120),
                no_speech_threshold=0.6,
            )

            valid_texts = []
            for seg in segments:
                # กรอง segment ที่โมเดลคำนวณว่าเป็นความเงียบหรือเสียงขยะ
                if getattr(seg, "no_speech_prob", 0.0) > 0.65:
                    continue
                seg_text = seg.text.strip()
                if seg_text:
                    valid_texts.append(seg_text)

            text = " ".join(valid_texts).strip()
            logger.info("Whisper output: '%s' (audio=%.1fs, peak=%.3f)", text, len(audio) / config.SAMPLE_RATE, peak)
        except Exception as e:
            logger.warning("Transcription error: %s", e)
            return ""

        elapsed = time.time() - start

        # กรองคำหลอนตอนท้ายวิดีโอ (YouTube Subtitle Hallucinations)
        known_hallucinations = [
            "โปรดติดตาม",
            "ติดตามต่อไป",
            "ตอนต่อไป",
            "ขอบคุณสำหรับการรับชม",
            "ขอบคุณที่รับชม",
            "กดติดตาม",
            "subscribe",
            "บ๊ายบาย",
        ]
        for hallu in known_hallucinations:
            if hallu in text:
                return ""

        # กรองกรณี Whisper เดาคำเดี่ยวๆ ตอนเสียงเบามาก
        if text in ("ขอบคุณครับ", "ขอบคุณค่ะ", "สวัสดีครับ", "สวัสดีค่ะ") and peak < 0.035:
            logger.debug("Filtered ghost hallucination '%s' at low peak %.4f", text, peak)
            return ""

        if text:
            logger.info("Transcribed in %.2fs: '%s'", elapsed, text)
        return text

    def detect_wake_word(self, text: str) -> tuple[bool, str]:
        """ตรวจสอบว่ามี wake word ในข้อความหรือไม่

        Args:
            text: ข้อความที่ถอดจากเสียง

        Returns:
            (found, command) — found=True ถ้าพบ wake word,
            command=ข้อความคำสั่ง
        """
        text_lower = text.lower().strip()

        # เรียงคำเรียกจากยาวไปสั้น เพื่อตรวจจับคำเฉพาะเจาะจงก่อน (เช่น ท่านมหาปราชญ์ ก่อน มหาปราชญ์)
        sorted_wakes = sorted(config.WAKE_WORD_ALTERNATIVES, key=len, reverse=True)

        for wake in sorted_wakes:
            wake_lower = wake.lower()
            if wake_lower in text_lower:
                idx = text_lower.index(wake_lower)
                command = text[idx + len(wake):].strip().lstrip(" ,.:;!?")
                # รองรับกรณีผู้ใช้พูดคำสั่งนำหน้า เช่น "เปิดยูทูป ราฟาเอล"
                if not command:
                    before = text[:idx].strip().rstrip(" ,.:;!?")
                    if len(before) >= 3:
                        command = before
                return True, command

        return False, ""


# ═══════════════════════════════════════════════════════════
#  TTS — Text-to-Speech (edge-tts)
# ═══════════════════════════════════════════════════════════

class TextToSpeech:
    """สังเคราะห์เสียงพูดภาษาไทยด้วย edge-tts (Microsoft Neural TTS)"""

    def __init__(self, on_amplitude: Optional[Callable[[float], None]] = None) -> None:
        """สร้าง TTS engine — โหลดครั้งเดียว ใช้ซ้ำตลอดเซสชัน"""
        # สร้างโฟลเดอร์ cache สำหรับไฟล์เสียงชั่วคราว
        os.makedirs(config.TTS_TEMP_DIR, exist_ok=True)
        # ล้างไฟล์เสียงชั่วคราวที่อาจค้างอยู่จากเซสชันก่อนหน้า
        try:
            for old_file in Path(config.TTS_TEMP_DIR).glob("*.mp3"):
                try:
                    old_file.unlink()
                except Exception:
                    pass
            for old_file in Path(config.TTS_TEMP_DIR).glob("*.wav"):
                try:
                    old_file.unlink()
                except Exception:
                    pass
        except Exception:
            pass

        self.is_speaking: bool = False
        self._default_on_amplitude = on_amplitude

        # ─── Queue + Worker (ขั้น B) ───
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_running: bool = False
        self._done_event: asyncio.Event = asyncio.Event()
        self._done_event.set()  # เริ่มต้นเป็น "เสร็จแล้ว"

        # ─── Barge-in (ขั้น C) ───
        self._cancel_event: asyncio.Event = asyncio.Event()

        logger.info("[VOICE] กำลังโหลด Voice Engine...")
        logger.info("[VOICE] Voice: %s", config.TTS_VOICE)
        logger.info("[VOICE] Rate: %s", config.TTS_RATE)
        logger.info("[VOICE] TTS พร้อมใช้งาน")

    # Pre-compiled Regex Patterns เพื่อประสิทธิภาพสูงสุดในการแปลงข้อความ
    _RE_CODE_BLOCK = re.compile(r'```.*?```', flags=re.DOTALL)
    _RE_INLINE_CODE = re.compile(r'`.*?`')
    _RE_MARKDOWN_LINK = re.compile(r'\[(.*?)\]\(.*?\)')
    _RE_TIME_COLON = re.compile(r'(\d{1,2}):(\d{2})(?:\s*น\.?)?')
    _RE_TIME_ABBR = re.compile(r'(\d+)\s*น\.')
    _RE_TIME_STANDALONE = re.compile(r'(?<!นาที\s)(?<!นาฬิกา\s)\bน\.')
    _RE_PERCENT = re.compile(r'(\d+)\s*%')
    _RE_DECIMAL = re.compile(r'(\d+)\.(\d+)')
    _RE_CELSIUS = re.compile(r'°[Cc]')
    _RE_SYMBOLS = re.compile(r'[:*•\-_#|/\\(){}\[\]<>"~+=@^&%$!?,;]')
    _RE_NON_WORD = re.compile(r'[^\w\s\u0E00-\u0E7F]')
    _RE_MULTI_SPACE = re.compile(r'\s+')

    @classmethod
    def _sanitize_for_tts(cls, text: str) -> str:
        """แปลงสัญลักษณ์ รูปแบบเวลา และตัวเลข ให้อ่านออกเสียงอย่างถูกต้อง นุ่มนวล ป้องกัน Edge-TTS และ gTTS ล้มเหลว 100%"""
        if not text:
            return "ดำเนินการเรียบร้อยแล้วครับ ท่านเจ้านาย"

        # 1. ลบ Markdown Code Blocks, Links และ Formatting
        text = cls._RE_CODE_BLOCK.sub(' ', text)
        text = cls._RE_INLINE_CODE.sub(' ', text)
        text = cls._RE_MARKDOWN_LINK.sub(r'\1', text)

        # 2. แปลงรูปแบบเวลา เช่น 19:52 น. -> 19 นาฬิกา 52 นาที (ป้องกันการอ่าน 'นาฬิกา' ซ้ำ)
        def _replace_time_colon(match: re.Match) -> str:
            hour = int(match.group(1))
            minute = int(match.group(2))
            if minute == 0:
                return f"{hour} นาฬิกาตรง"
            return f"{hour} นาฬิกา {minute} นาที"

        text = cls._RE_TIME_COLON.sub(_replace_time_colon, text)
        text = cls._RE_TIME_ABBR.sub(r'\1 นาฬิกา', text)
        text = cls._RE_TIME_STANDALONE.sub('นาฬิกา', text)

        # 3. แปลงตัวเลขทศนิยมและเปอร์เซ็นต์
        text = cls._RE_PERCENT.sub(r'\1 เปอร์เซ็นต์', text)
        text = cls._RE_DECIMAL.sub(r'\1 จุด \2', text)
        text = cls._RE_CELSIUS.sub(' องศาเซลเซียส', text)

        # 4. แปลงคำทับศัพท์ ตัวย่อคอมพิวเตอร์ และวลีที่อ่อนไหวให้อ่านออกเสียงอย่างเป็นธรรมชาติ
        term_replacements = [
            (re.compile(r'\bCPU\b', re.IGNORECASE), 'ระบบประมวลผล'),
            (re.compile(r'\bซีพียู\b'), 'ระบบประมวลผล'),
            (re.compile(r'\bRAM\b', re.IGNORECASE), 'หน่วยความจำ'),
            (re.compile(r'\bแรม\b'), 'หน่วยความจำ'),
            (re.compile(r'\bGB\b', re.IGNORECASE), 'กิกะไบต์'),
            (re.compile(r'\bMB\b', re.IGNORECASE), 'เมกะไบต์'),
            (re.compile(r'\bKB\b', re.IGNORECASE), 'กิโลไบต์'),
            (re.compile(r'\bTB\b', re.IGNORECASE), 'เทระไบต์'),
            (re.compile(r'\bYouTube\b', re.IGNORECASE), 'ยูทูป'),
            (re.compile(r'\bGoogle\b', re.IGNORECASE), 'กูเกิล'),
            (re.compile(r'\bChrome\b', re.IGNORECASE), 'โครม'),
            (re.compile(r'\bNotepad\b', re.IGNORECASE), 'โน้ตแพด'),
            (re.compile(r'\bWindows\b', re.IGNORECASE), 'วินโดวส์'),
            (re.compile(r'\bPC\b', re.IGNORECASE), 'คอมพิวเตอร์'),
            (re.compile(r'สถานะระบบ'), 'สถานะการทำงาน'),
            (re.compile(r'ปรับระดับเสียง'), 'ปรับระดับความดัง'),
            (re.compile(r'ปรับเสียง'), 'ปรับระดับความดัง'),
            (re.compile(r'เพิ่มเสียง'), 'เพิ่มระดับความดัง'),
            (re.compile(r'ลดเสียง'), 'ลดระดับความดัง'),
            (re.compile(r'ระดับเสียง'), 'ระดับความดัง'),
            (re.compile(r'ปิดเสียง'), 'ปิดเสียงการทำงาน'),
        ]
        for pattern, replacement in term_replacements:
            text = pattern.sub(replacement, text)

        # 5. ล้างสัญลักษณ์พิเศษ คอลอน, ขีด, ดอกจัน, ชาร์ป, วงเล็บ, อิโมจิ
        text = cls._RE_SYMBOLS.sub(' ', text)

        # 6. กรองเฉพาะพยัญชนะไทย, ภาษาอังกฤษ, ตัวเลข และช่องว่าง (ตัดอิโมจิและอักขระประหลาดที่ทำให้ TTS หลุด)
        text = cls._RE_NON_WORD.sub(' ', text)

        # 7. ยุบช่องว่างซ้ำซ้อน
        text = cls._RE_MULTI_SPACE.sub(' ', text).strip()

        if not text:
            return "ดำเนินการเรียบร้อยแล้วครับ ท่านเจ้านาย"

        return text

    async def synthesize(self, text: str) -> str:
        """สังเคราะห์เสียงจากข้อความ — ใช้เสียงจาก config เท่านั้น ไม่ fallback ไปเสียงอื่น

        Args:
            text: ข้อความที่ต้องการแปลงเป็นเสียง

        Returns:
            path ไปยังไฟล์เสียงที่สร้างขึ้น
        """
        output_path = os.path.join(
            config.TTS_TEMP_DIR,
            f"tts_{int(time.time() * 1000)}.mp3",
        )

        clean_text = self._sanitize_for_tts(text)

        # ─── Edge TTS (เสียงเดียวจาก config — ไม่ fallback) ───
        # Dynamic timeout: ข้อความยาวได้เวลามากขึ้น (+0.03s ต่ออักขระ)
        timeout = getattr(config, "TTS_TIMEOUT", 10.0) + len(clean_text) * 0.03

        try:
            communicate = edge_tts.Communicate(
                clean_text,
                config.TTS_VOICE,
                rate=config.TTS_RATE,
            )
            await asyncio.wait_for(communicate.save(output_path), timeout=timeout)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 200:
                logger.debug("TTS generated via Edge TTS (%s): %s", config.TTS_VOICE, output_path)
                return output_path
        except asyncio.TimeoutError:
            logger.error(
                "[VOICE][ERROR] Edge TTS timeout (%.1fs) — ข้อความ %d ตัวอักษร — ไม่สลับเสียง",
                timeout, len(clean_text),
            )
        except Exception as e:
            logger.error("[VOICE][ERROR] Edge TTS (%s) failed: %s — ไม่สลับเสียง", config.TTS_VOICE, e)

        raise RuntimeError(f"TTS synthesis failed for voice {config.TTS_VOICE}")

    async def speak(
        self,
        text: str,
        on_amplitude: Optional[Callable[[float], None]] = None,
    ) -> None:
        """สังเคราะห์เสียงแล้วเล่นทันที (backward compatible — ใช้สำหรับประโยคสั้น)

        สำหรับข้อความยาว ใช้ enqueue() + wait_until_done() แทน

        Args:
            text: ข้อความที่ต้องการพูด
            on_amplitude: callback ฟังก์ชันรับค่าความดังเสียง (0.0-1.0)
        """
        if not text or not text.strip():
            return

        logger.info("Speaking: %s", text[:80])
        self.is_speaking = True
        self._cancel_event.clear()
        cb = on_amplitude if on_amplitude is not None else self._default_on_amplitude

        try:
            audio_path = await self.synthesize(text)

            if self._cancel_event.is_set():
                self._cleanup_file(audio_path)
                return

            await self.play_audio(audio_path, on_amplitude=cb)

            # Echo Guard: เว้นระยะ 0.4 วินาทีให้เสียงก้องลำโพงและบัฟเฟอร์ในห้องสลายตัว
            await asyncio.sleep(0.4)

            self._cleanup_file(audio_path)

        except Exception as e:
            logger.error("TTS error: %s", e, exc_info=True)
        finally:
            if cb:
                try:
                    cb(0.0)
                except Exception:
                    pass
            self.is_speaking = False

    # ─── Queue / Chunking / Worker (ขั้น B) ─────────────────────

    @staticmethod
    def _split_text(text: str, max_chunk: int = 120) -> list[str]:
        """แบ่งข้อความเป็นช่วงสั้นๆ อย่างเป็นธรรมชาติสำหรับภาษาไทยและภาษาอังกฤษ
        แบ่งตามเครื่องหมายจบประโยค, ขึ้นบรรทัดใหม่, คำลงท้ายสุภาพ (ครับ/ค่ะ), และช่องว่าง

        Args:
            text: ข้อความที่ต้องการแบ่ง
            max_chunk: ขนาดสูงสุดต่อช่วง (ตัวอักษร)

        Returns:
            list ของช่วงข้อความ
        """
        if not text or not text.strip():
            return []

        # 1. แยกตามการขึ้นบรรทัดใหม่ก่อน
        lines = [line.strip() for line in re.split(r'[\r\n]+', text) if line.strip()]

        sub_clauses: list[str] = []
        polite_endings = ("ครับผม", "นะครับ", "นะคะ", "ครับ", "ค่ะ", "จ้า", "นะ")

        for line in lines:
            # ในภาษาไทย ประโยคย่อยจะคั่นด้วยช่องว่าง
            tokens = line.split()
            current = ""
            for token in tokens:
                if not current:
                    current = token
                else:
                    current += " " + token

                ends_with_polite = any(current.endswith(p) for p in polite_endings)
                ends_with_punct = current[-1] in ".!?…,"
                # ถ้าลงท้ายด้วยคำสุภาพหรือเครื่องหมายวรรคตอน และยาวพอสมควร (>= 20 ตัวอักษร) ให้ตัดเป็นช่วง
                if (ends_with_polite or ends_with_punct) and len(current) >= 20:
                    sub_clauses.append(current.strip())
                    current = ""
                elif len(current) >= max_chunk:
                    sub_clauses.append(current.strip())
                    current = ""

            if current.strip():
                sub_clauses.append(current.strip())

        # 2. รวมช่วงที่สั้นเกินไป (< 25 ตัวอักษร) เข้าด้วยกันเพื่อความลื่นไหลของเสียง
        merged: list[str] = []
        for clause in sub_clauses:
            if merged and len(merged[-1]) + len(clause) + 1 <= max_chunk and (len(merged[-1]) < 25 or len(clause) < 15):
                merged[-1] += " " + clause
            else:
                merged.append(clause)

        return merged if merged else [text.strip()]

    def enqueue(self, text: str) -> None:
        """แบ่งข้อความเป็นช่วง แล้วใส่คิว — return ทันที ไม่ await

        Args:
            text: ข้อความที่ต้องการพูด
        """
        if not text or not text.strip():
            return

        self._cancel_event.clear()
        chunks = self._split_text(text)
        logger.info("[VOICE] Enqueue %d chunk(s): %s", len(chunks), text[:80])

        for chunk in chunks:
            self._queue.put_nowait(chunk)

        if not self._worker_running:
            self._done_event.clear()
            asyncio.create_task(self._worker())

    async def _worker(self) -> None:
        """Worker loop — ดึงจากคิว → สังเคราะห์ → เล่น ทีละช่วง พร้อม prefetch"""
        self._worker_running = True
        self._done_event.clear()
        cb = self._default_on_amplitude

        prefetch_task: Optional[asyncio.Task] = None

        try:
            while True:
                if self._cancel_event.is_set():
                    if prefetch_task:
                        if not prefetch_task.done():
                            prefetch_task.cancel()
                            try:
                                await prefetch_task
                            except (asyncio.CancelledError, Exception):
                                pass
                        else:
                            try:
                                self._cleanup_file(prefetch_task.result())
                            except Exception:
                                pass
                        prefetch_task = None
                    self._drain_queue()
                    break

                # ─── ดึงเสียงจาก prefetch หรือสังเคราะห์ใหม่ ───
                audio_path: Optional[str] = None

                if prefetch_task is not None:
                    try:
                        audio_path = await prefetch_task
                    except Exception as e:
                        logger.error("[VOICE][ERROR] Prefetch synthesis failed: %s", e)
                    prefetch_task = None
                    if audio_path is None:
                        continue
                else:
                    try:
                        text = self._queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    try:
                        audio_path = await self.synthesize(text)
                    except Exception as e:
                        logger.error("[VOICE][ERROR] Synthesis failed for chunk: %s", e)
                        continue

                if self._cancel_event.is_set():
                    self._cleanup_file(audio_path)
                    if prefetch_task:
                        if not prefetch_task.done():
                            prefetch_task.cancel()
                        else:
                            try:
                                self._cleanup_file(prefetch_task.result())
                            except Exception:
                                pass
                        prefetch_task = None
                    self._drain_queue()
                    break

                self.is_speaking = True

                # ─── Prefetch: สังเคราะห์ช่วงถัดไปขณะเล่นช่วงปัจจุบัน ───
                if not self._queue.empty() and not self._cancel_event.is_set():
                    try:
                        next_text = self._queue.get_nowait()
                        prefetch_task = asyncio.create_task(self.synthesize(next_text))
                    except asyncio.QueueEmpty:
                        pass

                # ─── เล่นเสียง ───
                await self.play_audio(audio_path, on_amplitude=cb)

                # Echo guard: สั้นลงระหว่างช่วง, ยาวขึ้นตอนจบ
                if not self._cancel_event.is_set():
                    if not self._queue.empty() or prefetch_task is not None:
                        await asyncio.sleep(0.15)
                    else:
                        await asyncio.sleep(0.4)

                self._cleanup_file(audio_path)

        finally:
            if prefetch_task:
                if not prefetch_task.done():
                    prefetch_task.cancel()
                else:
                    try:
                        self._cleanup_file(prefetch_task.result())
                    except Exception:
                        pass
                prefetch_task = None
            self.is_speaking = False
            self._worker_running = False
            self._done_event.set()
            if cb:
                try:
                    cb(0.0)
                except Exception:
                    pass

    # ─── Barge-in / Stop (ขั้น C) ────────────────────────────────

    def stop(self) -> None:
        """หยุดเสียงทันที ล้างคิว — ใช้สำหรับ barge-in"""
        logger.info("[VOICE] Stop — clearing queue and stopping playback")
        self._cancel_event.set()
        sd.stop()
        self._drain_queue()
        self.is_speaking = False
        self._done_event.set()  # ปลดบล็อก wait_until_done() ทันที
        if self._default_on_amplitude:
            try:
                self._default_on_amplitude(0.0)
            except Exception:
                pass

    async def wait_until_done(self) -> None:
        """รอจนพูดจบทุกช่วงในคิว"""
        await self._done_event.wait()

    def _drain_queue(self) -> None:
        """ล้างคิวทั้งหมด"""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    @staticmethod
    def _cleanup_file(path: Optional[str]) -> None:
        """ลบไฟล์เสียงชั่วคราว"""
        if path:
            try:
                os.remove(path)
            except OSError:
                pass

    async def play_audio(
        self,
        file_path: str,
        on_amplitude: Optional[Callable[[float], None]] = None,
    ) -> None:
        """เล่นไฟล์เสียง .mp3/.wav ผ่าน sounddevice พร้อมสตรีม amplitude สำหรับ animation sync

        Args:
            file_path: path ไปยังไฟล์เสียง
            on_amplitude: callback สตรีม amplitude ทุกๆ 33ms (~30 FPS)
        """
        try:
            data, samplerate = sf.read(file_path, dtype="float32")
        except Exception as e:
            logger.error("Failed to read audio file %s: %s", file_path, e)
            return

        if on_amplitude is None:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._play_blocking, data, samplerate)
            return

        try:
            # คำนวณ amplitude ตรงจากข้อมูลใน RAM ไม่ต้องอ่านไฟล์ซ้ำ
            amplitudes = self.calculate_amplitudes(data, samplerate)
            sd.play(data, samplerate)

            start_time = time.time()
            for idx, amp in enumerate(amplitudes):
                # ─── Barge-in: หยุดทันทีถ้ามีสัญญาณยกเลิก ───
                if self._cancel_event.is_set():
                    sd.stop()
                    break
                try:
                    on_amplitude(amp)
                except Exception:
                    pass
                target_time = start_time + (idx + 1) * 0.033
                sleep_sec = target_time - time.time()
                if sleep_sec > 0:
                    await asyncio.sleep(sleep_sec)

            # รอจนเสียงจบจริงตาม duration (ข้ามถ้า barge-in)
            if not self._cancel_event.is_set():
                total_duration = len(data) / samplerate
                remaining = total_duration - (time.time() - start_time)
                if remaining > 0:
                    await asyncio.sleep(remaining)

        except Exception as e:
            logger.error("sounddevice output error: %s", e)
        finally:
            sd.stop()
            if on_amplitude:
                try:
                    on_amplitude(0.0)
                except Exception:
                    pass

    @staticmethod
    def _play_blocking(data: np.ndarray, samplerate: int) -> None:
        """เล่นเสียงแบบ blocking (สำหรับ run_in_executor)"""
        try:
            sd.play(data, samplerate)
            sd.wait()
        finally:
            sd.stop()

    @staticmethod
    def calculate_amplitudes(data: np.ndarray, samplerate: int, frame_sec: float = 0.033) -> list[float]:
        """คำนวณ amplitude สำหรับ animation sync จาก audio array ในหน่วยความจำตรงๆ

        Args:
            data: audio samples array (float32)
            samplerate: อัตราสุ่มตัวอย่างเสียง
            frame_sec: ความยาวแต่ละ frame (~33ms หรือ ~30fps)

        Returns:
            list ของ amplitude ค่า (0.0-1.0)
        """
        try:
            samples = data.mean(axis=1) if data.ndim > 1 else data
            frame_size = int(samplerate * frame_sec)
            if frame_size <= 0:
                return []

            amplitudes: list[float] = []
            for i in range(0, len(samples), frame_size):
                frame = samples[i : i + frame_size]
                rms = float(np.sqrt(np.mean(frame**2))) if len(frame) > 0 else 0.0
                amplitudes.append(min(1.0, rms * 5.0))
            return amplitudes
        except Exception:
            return []

    def get_audio_amplitude(self, file_path: str) -> list[float]:
        """อ่าน amplitude จากไฟล์เสียง (คงไว้เพื่อ backward compatibility)"""
        try:
            data, samplerate = sf.read(file_path, dtype="float32")
            return self.calculate_amplitudes(data, samplerate)
        except Exception:
            return []
