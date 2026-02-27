"""FFmpeg-based media processing: probe, extract audio, split into chunks.

Handles MP4, MOV, MP3, WAV, MKV, AVI, WEBM, FLAC, OGG, AAC, M4A.
All splitting is done via ffmpeg so there is zero audio drift between
chunk boundaries, quality is preserved, and memory usage stays constant
regardless of file size.
"""

import subprocess
import json
import os
import math
import shutil
import tempfile


def probe_duration(file_path):
    """Return media duration in seconds using ffprobe (no file loading)."""
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'json',
        file_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f'ffprobe failed: {result.stderr.strip()}')
    data = json.loads(result.stdout)
    dur = data.get('format', {}).get('duration')
    if dur is None:
        raise RuntimeError('Could not determine media duration')
    return float(dur)


def probe_media(file_path):
    """Return detailed media info dict."""
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries',
        'format=duration,size,format_name:stream=codec_type,codec_name,sample_rate,channels',
        '-of', 'json',
        file_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f'ffprobe failed: {result.stderr.strip()}')
    data = json.loads(result.stdout)
    fmt = data.get('format', {})
    streams = data.get('streams', [])
    return {
        'duration': float(fmt.get('duration', 0)),
        'size': int(fmt.get('size', 0)),
        'format': fmt.get('format_name', ''),
        'has_video': any(s.get('codec_type') == 'video' for s in streams),
        'has_audio': any(s.get('codec_type') == 'audio' for s in streams),
    }


def prepare_audio(input_path, output_wav_path):
    """Convert any audio/video to 16 kHz mono PCM WAV (single ffmpeg pass).

    Strips video track, resamples to 16 kHz, forces mono — ideal input for
    speech-recognition engines.  Works with all ffmpeg-supported formats.
    """
    cmd = [
        'ffmpeg', '-y',
        '-i', input_path,
        '-vn',
        '-acodec', 'pcm_s16le',
        '-ar', '16000',
        '-ac', '1',
        output_wav_path,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=1200)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors='replace')[-500:]
        raise RuntimeError(f'Audio extraction failed: {stderr}')
    return output_wav_path


def split_audio_chunks(wav_path, chunk_dir, chunk_duration, total_duration,
                       progress_cb=None):
    """Split a 16 kHz mono WAV into sequential chunks.

    Uses input-seeking (-ss before -i) which is byte-exact for PCM WAV and
    runs in O(1) per chunk regardless of file length.

    Returns list of dicts: [{'path', 'index', 'start', 'end'}, ...]
    """
    num_chunks = math.ceil(total_duration / chunk_duration)
    os.makedirs(chunk_dir, exist_ok=True)
    chunks = []

    for i in range(num_chunks):
        start = round(i * chunk_duration, 3)
        actual_dur = round(min(chunk_duration, total_duration - start), 3)
        end = round(start + actual_dur, 3)

        if actual_dur < 0.2:
            continue

        chunk_path = os.path.join(chunk_dir, f'chunk_{i:04d}.wav')
        cmd = [
            'ffmpeg', '-y',
            '-ss', f'{start:.3f}',
            '-i', wav_path,
            '-t', f'{actual_dur:.3f}',
            '-acodec', 'pcm_s16le',
            '-ar', '16000',
            '-ac', '1',
            chunk_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode != 0:
            continue

        chunks.append({
            'path': chunk_path,
            'index': i,
            'start': start,
            'end': end,
        })

        if progress_cb:
            progress_cb(i + 1, num_chunks, f'Splitting chunk {i + 1}/{num_chunks}')

    return chunks


class MediaProcessor:
    """High-level pipeline: probe → convert → split.

    Usage::

        with MediaProcessor(chunk_duration=10.0) as mp:
            chunks, duration = mp.process('video.mp4')
            for c in chunks:
                transcribe(c['path'])  # 16 kHz mono WAV
    """

    def __init__(self, chunk_duration=10.0):
        self.chunk_duration = chunk_duration
        self._temp_dir = None
        self._wav_path = None

    # ------------------------------------------------------------------
    def process(self, input_path, progress_cb=None):
        """Run the full pipeline.  Returns ``(chunks, duration)``."""
        self._temp_dir = tempfile.mkdtemp(prefix='somali_media_')

        if progress_cb:
            progress_cb(0, 1, 'Analyzing media...')
        duration = probe_duration(input_path)

        if progress_cb:
            progress_cb(0, 1, 'Extracting audio...')
        self._wav_path = os.path.join(self._temp_dir, 'full_audio.wav')
        prepare_audio(input_path, self._wav_path)

        chunk_dir = os.path.join(self._temp_dir, 'chunks')
        chunks = split_audio_chunks(
            self._wav_path, chunk_dir,
            self.chunk_duration, duration,
            progress_cb=progress_cb,
        )

        return chunks, duration

    # ------------------------------------------------------------------
    def cleanup(self):
        if self._temp_dir and os.path.isdir(self._temp_dir):
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cleanup()
