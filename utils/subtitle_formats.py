"""Convert segment lists to SRT and VTT strings."""


def _sec_to_srt_ts(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _sec_to_vtt_ts(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def segments_to_srt(segments):
    """segments: list of dicts with start_sec/end_sec or start/end (seconds) and text."""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = seg.get("start_sec", seg.get("start", 0))
        end = seg.get("end_sec", seg.get("end", 0))
        text = (seg.get("text") or "").strip()
        lines.append(f"{i}\n{_sec_to_srt_ts(start)} --> {_sec_to_srt_ts(end)}\n{text}\n")
    return "\n".join(lines) if lines else ""


def segments_to_vtt(segments):
    head = "WEBVTT\n\n"
    body = []
    for seg in segments:
        start = seg.get("start_sec", seg.get("start", 0))
        end = seg.get("end_sec", seg.get("end", 0))
        text = (seg.get("text") or "").strip()
        body.append(f"{_sec_to_vtt_ts(start)} --> {_sec_to_vtt_ts(end)}\n{text}")
    return head + "\n\n".join(body) if body else head
