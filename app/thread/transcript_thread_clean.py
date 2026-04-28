import datetime
import os
import tempfile
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from app.config import CACHE_PATH
from app.core.bk_asr import transcribe
from app.core.entities import TranscribeModelEnum, TranscribeTask
from app.core.storage.cache_manager import ServiceUsageManager
from app.core.storage.database import DatabaseManager
from app.core.utils.logger import setup_logger
from app.core.utils.video_utils import video2audio

logger = setup_logger("transcript_thread")


class TranscriptThread(QThread):
    finished = pyqtSignal(TranscribeTask)
    progress = pyqtSignal(int, str)
    error = pyqtSignal(str)
    MAX_DAILY_ASR_CALLS = 40

    def __init__(self, task: TranscribeTask):
        super().__init__()
        self.task = task
        db_manager = DatabaseManager(CACHE_PATH)
        self.service_manager = ServiceUsageManager(db_manager)

    def run(self):
        temp_file = None
        force_no_asr_cache = False
        try:
            logger.info("\n===========转录任务开始===========")
            logger.info("时间：%s", datetime.datetime.now())

            video_path = Path(self.task.file_path)
            if not video_path.exists():
                logger.error("视频文件不存在：%s", video_path)
                raise ValueError(self.tr("视频文件不存在"))

            if self.task.transcribe_config.transcribe_model in [
                TranscribeModelEnum.BIJIAN,
                TranscribeModelEnum.JIANYING,
            ]:
                if not self.service_manager.check_service_available(
                    "asr", self.MAX_DAILY_ASR_CALLS
                ):
                    raise Exception(
                        self.tr("公益ASR服务已达到每日使用限制，建议使用本地转录")
                    )

            if self.task.need_next_task:
                subtitle_dir = Path(self.task.file_path).parent / "subtitle"
                downloaded_subtitles = (
                    list(subtitle_dir.glob("【下载字幕】*")) if subtitle_dir.exists() else []
                )
                if downloaded_subtitles:
                    force_no_asr_cache = True
                    logger.info(
                        "找到已下载字幕文件，但本次任务会忽略它们并重新执行转录：%s",
                        downloaded_subtitles[0],
                    )

            output_path = Path(self.task.output_path)
            if output_path.exists():
                force_no_asr_cache = True
                logger.info("输出字幕文件已存在，将覆盖写入：%s", output_path)

            if force_no_asr_cache and self.task.transcribe_config.use_asr_cache:
                logger.info("检测到本次属于重新转录，已强制禁用 ASR 缓存")
                self.task.transcribe_config.use_asr_cache = False

            self.progress.emit(5, self.tr("转换音频中"))
            logger.info("开始转换音频")

            temp_dir = tempfile.gettempdir()
            temp_file = tempfile.NamedTemporaryFile(
                suffix=".wav", dir=temp_dir, delete=False
            )
            temp_file.close()

            is_success = video2audio(str(video_path), output=temp_file.name)
            if not is_success:
                logger.error("音频转换失败")
                raise RuntimeError(self.tr("音频转换失败"))

            self.progress.emit(20, self.tr("语音转录中"))
            logger.info("开始语音转录")

            asr_data = transcribe(
                temp_file.name,
                self.task.transcribe_config,
                callback=self.progress_callback,
            )

            if self.task.transcribe_config.transcribe_model in [
                TranscribeModelEnum.BIJIAN,
                TranscribeModelEnum.JIANYING,
            ]:
                self.service_manager.increment_usage("asr", self.MAX_DAILY_ASR_CALLS)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            if self.task.need_next_task:
                sidecar_path = output_path.with_name(f"{output_path.stem}.asr.json")
                asr_data.save(save_path=str(sidecar_path))
                asr_data.to_srt(save_path=str(output_path), include_speaker=False)
            else:
                asr_data.to_srt(save_path=str(output_path), include_speaker=True)
            logger.info("字幕文件已保存到: %s", str(output_path))

            self.progress.emit(100, self.tr("转录完成"))
            self.finished.emit(self.task)
        except Exception as e:
            logger.exception("转录过程中发生错误: %s", str(e))
            self.error.emit(str(e))
            self.progress.emit(100, self.tr("转录失败"))
        finally:
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except Exception as e:
                    logger.warning("清理临时文件失败: %s", e)

    def progress_callback(self, value, message):
        progress = min(20 + (value * 0.8), 100)
        self.progress.emit(int(progress), message)
