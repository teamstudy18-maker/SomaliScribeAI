# SomaliScribe AI

An AI-powered web app that generates Somali subtitles from audio and video files. Upload media, edit subtitles in the browser, and export SRT, VTT, or a video with burned-in captions.

## Features

- **Web interface**: Dark-themed UI (SomaliScribe AI) with Home, Upload, Editor, and History
- **User management**: Register, login, guest mode, role-based access (User, Admin)
- **Media upload**: Audio (MP3, WAV, M4A, FLAC, OGG, AAC) and video (MP4, MKV, AVI). File size limit 100MB. Upload progress indicator
- **Somali ASR**: Automatic speech recognition using Google Speech Recognition (so-SO) with dataset fallback (6,751 Somali audio entries)
- **Subtitle generation**: Time-aligned segments; supports SRT and VTT
- **Subtitle editor**: Edit text, adjust timestamps, merge/split segments, live caption preview with customizable font and colors
- **Export & download**: Download SRT or VTT; burn subtitles into video (or generate a video from audio + subtitles)
- **History**: Per-user job history with links to edit, export, and burn-in
- **Admin panel**: Manage users, files, and view transcription statistics

## Dataset Structure

```
dataset/
├── metadata.csv      # Audio entries with transcriptions
├── train.csv
├── validation.csv
├── test.csv
└── wavs/             # Audio files (.wav)
```

## Installation

1. **Python**: 3.7 or higher  
2. **Create and activate a virtual environment** (recommended):

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Linux/macOS
```

3. **Install dependencies**:

```bash
pip install -r requirements.txt
```

4. **PostgreSQL**: Install PostgreSQL (v16+) and create the database:

```bash
psql -U postgres
CREATE DATABASE somali_subtitles;
\q
```

By default the app connects to `postgresql://postgres:postgres@localhost:5432/somali_subtitles`.
Override with the `DATABASE_URI` environment variable:

```bash
set DATABASE_URI=postgresql://user:pass@host:5432/dbname
```

5. **ffmpeg** (for video upload and burn-in): Install from [ffmpeg.org](https://ffmpeg.org/) or `winget install ffmpeg` and ensure it is on your PATH.

## Quick Start

1. **Initialize the database**:

```bash
flask --app app init-db
```

2. **Create an admin user** (optional):

```bash
flask --app app create-admin your@email.com yourpassword
```

3. **Run the app**:

```bash
flask --app app run --debug --port 5000
```

4. Open **http://127.0.0.1:5000** in your browser.

## Usage

- **Home**: Landing page with “Start Creating” and feature overview.
- **Upload** (via “Start Creating” or `/create`): Drag-and-drop or select a file, then click “Generate Subtitles”. When processing finishes, you are redirected to the editor.
- **Editor**: Play media, edit segment text and timestamps, merge/split/delete segments, change caption style (font, size, colors). Use “Save”, “SRT”, “VTT”, and “Download Video with Subtitles” (burn-in for both video and audio jobs).
- **History** (logged-in users): List of your jobs with Edit, SRT, VTT, and Burn-in links.
- **Admin** (`/admin`): Dashboard, user management, file management, and stats (admin users only).

## Requirements

- Python 3.7+
- Flask, Flask-Login, Flask-SQLAlchemy, psycopg2-binary
- PostgreSQL (v16+)
- pandas, librosa, numpy, SpeechRecognition, pydub, scipy, soundfile
- **ffmpeg**: Required for video upload (audio extraction) and for “Download Video with Subtitles” (burn-in)

## Notes

- Internet connection required for Google Speech Recognition (Somali: so-SO).
- Dataset provides fallback when online recognition fails.
- Guest users can upload and use the editor; jobs are stored with `user_id = NULL`.
- Burn-in on Windows: SRT path escaping is handled for Windows drive letters and paths.

## Troubleshooting

| Issue | Suggestion |
|-------|------------|
| **Module not found** | Use the project venv and run `pip install -r requirements.txt` from the project root. |
| **Burn-in fails** | Install ffmpeg and ensure it is on PATH (`ffmpeg -version`). On Windows, use the fixed path escaping in the app. |
| **Upload/processing fails** | Check file format and size (max 100MB). For video, ffmpeg must be available for audio extraction. |
| **Speech recognition fails** | Check internet connection for Google API; dataset fallback may still produce subtitles. |

## Project structure

```
├── app.py              # Flask app, routes, upload, editor, burn-in
├── main.py             # SomaliSubtitleGenerator (ASR + segment generation)
├── extensions.py       # Flask-SQLAlchemy, Flask-Login
├── models/             # User, Job
├── routes/             # auth, admin blueprints
├── utils/              # subtitle_formats (SRT, VTT)
├── templates/          # Jinja2 (base, index, create, editor, history, admin)
├── requirements.txt
├── run_app.py          # Optional run script
└── dataset/            # Somali audio dataset (see above)

```
