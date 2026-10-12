import io
import os
import tempfile
import wave

import numpy as np
import soundfile as sf
from PyQt5.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer

import config as cf


class ResultSound(QObject):
    """Decode both short phrases before playing one continuous PCM file."""

    changed = pyqtSignal()
    failed = pyqtSignal(str)
    RANK_FILES = {"Giỏi": "GIOI.mp3", "Khá": "KHA.mp3",
                  "Đạt": "DAT.mp3", "Không đạt": "KDAT.mp3"}
    SAMPLE_RATE = 44100
    CHANNELS = 2
    GAP_MS = 120
    FADE_MS = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.port_id = None
        self._rank = None
        self._playing = False
        self._audio_dir = None
        self._player = QMediaPlayer(self)
        self._player.mediaStatusChanged.connect(self._on_status)
        self._player.error.connect(self._on_error)
        self._prepare_timer = QTimer(self)
        self._prepare_timer.setSingleShot(True)
        self._prepare_timer.timeout.connect(self._prepare_sentence)

    def start(self, port_id, rank):
        if self.port_id is not None or port_id not in (1, 2, 3, 4) or rank not in self.RANK_FILES:
            return
        self.port_id = port_id
        self._rank = rank
        self.changed.emit()
        self._prepare_timer.start(0)

    @classmethod
    def _read_pcm(cls, path):
        samples, rate = sf.read(path, dtype="int16", always_2d=True)
        if not len(samples) or rate <= 0 or samples.shape[1] not in (1, 2):
            raise ValueError("Bản ghi phải có dữ liệu âm thanh mono hoặc stereo.")
        if samples.shape[1] == 1:
            samples = np.repeat(samples, cls.CHANNELS, axis=1)
        if rate != cls.SAMPLE_RATE:
            # Speech clips may use different rates (DAT.mp3 is 22.05 kHz mono).
            count = max(1, round(len(samples) * cls.SAMPLE_RATE / rate))
            positions = np.arange(count) * rate / cls.SAMPLE_RATE
            original = np.arange(len(samples))
            samples = np.column_stack([
                np.interp(positions, original, samples[:, channel])
                for channel in range(cls.CHANNELS)
            ])
        return np.rint(samples).astype("<i2").tobytes()

    @classmethod
    def _sentence_wav(cls, clips):
        """Keep phrase levels; taper only the outer 5 ms to avoid edge clicks."""
        gap = bytes(cls.SAMPLE_RATE * cls.GAP_MS // 1000 * cls.CHANNELS * 2)
        faded = []
        for clip in clips:
            samples = np.frombuffer(clip, dtype="<i2").reshape(-1, cls.CHANNELS).copy()
            count = min(cls.SAMPLE_RATE * cls.FADE_MS // 1000, len(samples) // 2)
            if count:
                ramp = np.linspace(0, 1, count)[:, None]
                samples[:count] = np.rint(samples[:count] * ramp)
                samples[-count:] = np.rint(samples[-count:] * ramp[::-1])
            faded.append(samples.tobytes())
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(cls.CHANNELS)
            wav.setsampwidth(2)
            wav.setframerate(cls.SAMPLE_RATE)
            wav.writeframes(gap.join(faded))
        return output.getvalue()

    def _prepare_sentence(self):
        if self.port_id is None:
            return
        try:
            clips = [self._read_pcm(os.path.join(cf.DATA_DIR, "assets", "sounds", name))
                     for name in (f"Beso{self.port_id}.mp3", self.RANK_FILES[self._rank])]
            data = self._sentence_wav(clips)
            # Use a closed native file: DirectShow may block on a QIODevice stream.
            self._audio_dir = tempfile.TemporaryDirectory(prefix="mbt03-result-")
            path = os.path.join(self._audio_dir.name, "result.wav")
            with open(path, "wb") as output:
                output.write(data)
        except (OSError, ValueError, sf.SoundFileError) as error:
            self._fail(f"Không chuẩn bị được âm thanh kết quả: {error}")
            return
        self._playing = True
        self._player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
        if self._playing:
            self._player.setPlaybackRate(1.0)
            self._player.play()

    def _on_status(self, status):
        if status == QMediaPlayer.EndOfMedia and self._playing:
            self.stop()

    def _on_error(self, error):
        if error != QMediaPlayer.NoError and self.port_id is not None:
            self._fail(f"Không phát được kết quả: {self._player.errorString()}")

    def _fail(self, message):
        self.stop()
        self.failed.emit(message)

    def stop(self):
        active = self.port_id is not None
        self.port_id = None
        self._rank = None
        self._prepare_timer.stop()
        self._playing = False
        self._player.stop()
        # Release the native file handle before removing the temporary WAV.
        self._player.setMedia(QMediaContent())
        if self._audio_dir is not None:
            try:
                self._audio_dir.cleanup()
            except OSError as error:
                print(f"[Audio] Khong xoa duoc file ket qua tam: {error!a}")
            self._audio_dir = None
        if active:
            self.changed.emit()
