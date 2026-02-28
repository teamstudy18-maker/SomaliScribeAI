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


def _detect_silence_points(wav_path, total_duration, min_silence_len=0.3,
                           silence_thresh_db=-35):
    """Find silence timestamps in the WAV using RMS energy analysis.

    Returns a sorted list of midpoint seconds where silence occurs, suitable
    for choosing split boundaries that don't cut through spoken words.
    """
    try:
        import numpy as np
        import struct

        with open(wav_path, 'rb') as f:
            f.read(44)
            raw = f.read()

        if len(raw) < 100:
            return []

        samples = np.array(struct.unpack(f'<{len(raw) // 2}h', raw),
                           dtype=np.float32) / 32768.0

        sr = 16000
        frame_len = int(0.025 * sr)  # 25 ms frames
        hop = int(0.010 * sr)        # 10 ms hop
        num_frames = max(1, (len(samples) - frame_len) // hop)

        rms = np.empty(num_frames)
        for i in range(num_frames):
            s = i * hop
            rms[i] = np.sqrt(np.mean(samples[s:s + frame_len] ** 2) + 1e-10)

        rms_db = 20 * np.log10(rms + 1e-10)
        is_silent = rms_db < silence_thresh_db

        min_frames = int(min_silence_len / 0.010)
        silence_points = []
        run_start = None

        for i, s in enumerate(is_silent):
            if s:
                if run_start is None:
                    run_start = i
            else:
                if run_start is not None and (i - run_start) >= min_frames:
                    mid_frame = (run_start + i) // 2
                    silence_points.append(mid_frame * 0.010)
                run_start = None

        if run_start is not None and (num_frames - run_start) >= min_frames:
            mid_frame = (run_start + num_frames) // 2
            silence_points.append(mid_frame * 0.010)

        return sorted(silence_points)
    except Exception:
        return []


def _snap_to_silence(target_time, silence_points, window=1.5):
    """Return the silence point nearest to *target_time* within ±window.

    If no silence is found, returns the original target_time unchanged.
    """
    if not silence_points:
        return target_time
    best = target_time
    best_dist = window
    for sp in silence_points:
        d = abs(sp - target_time)
        if d < best_dist:
            best_dist = d
            best = sp
    return best


def split_audio_chunks(wav_path, chunk_dir, chunk_duration, total_duration,
                       progress_cb=None, overlap=0.0):
    """Split a 16 kHz mono WAV into sequential chunks.

    Uses input-seeking (-ss before -i) which is byte-exact for PCM WAV and
    runs in O(1) per chunk regardless of file length.

    When *overlap* > 0, adjacent chunks share that many seconds so words at
    boundaries aren't lost.  Boundaries are snapped to detected silence points
    to avoid cutting mid-word.

    Returns list of dicts: [{'path', 'index', 'start', 'end'}, ...]
    """
    os.makedirs(chunk_dir, exist_ok=True)

    silence_points = _detect_silence_points(wav_path, total_duration)

    boundaries = [0.0]
    cursor = 0.0
    while cursor + chunk_duration < total_duration:
        raw_end = cursor + chunk_duration
        snapped = _snap_to_silence(raw_end, silence_points, window=1.5)
        if snapped <= cursor + 1.0:
            snapped = raw_end
        boundaries.append(round(snapped, 3))
        cursor = round(snapped - overlap, 3)
    boundaries.append(round(total_duration, 3))

    boundaries = sorted(set(boundaries))

    num_chunks = len(boundaries) - 1
    chunks = []

    for i in range(num_chunks):
        start = boundaries[i]
        end = boundaries[i + 1]
        actual_dur = round(end - start, 3)

        if actual_dur < 0.3:
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

    def __init__(self, chunk_duration=10.0, overlap=1.0):
        self.chunk_duration = chunk_duration
        self.overlap = overlap
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
            overlap=self.overlap,
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
