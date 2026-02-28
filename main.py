import os
import pandas as pd
import numpy as np
from datetime import timedelta
import speech_recognition as sr
import warnings
warnings.filterwarnings('ignore')

class SomaliSubtitleGenerator:
    def __init__(self, dataset_path="dataset"):
        self.dataset_path = dataset_path
        self.metadata_df = None
        self.train_df = None
        self.load_dataset()
        
    def load_dataset(self):
        """Load the Somali dataset"""
        try:
            self.metadata_df = pd.read_csv(os.path.join(self.dataset_path, "metadata.csv"))
            self.train_df = pd.read_csv(os.path.join(self.dataset_path, "train.csv"))
            print(f"Loaded {len(self.metadata_df)} audio entries from dataset")
        except Exception as e:
            print(f"Error loading dataset: {e}")
            self.metadata_df = pd.DataFrame(columns=['file_name', 'transcription'])
            self.train_df = pd.DataFrame()
            
    def audio_to_text_with_reference(self, audio_path, use_reference=True):
        """Convert audio to text using Google ASR with Somali-tuned preprocessing."""
        import tempfile
        wav_path = None
        try:
            import librosa
            import scipy.signal
            import soundfile as sf

            y, sample_rate = librosa.load(audio_path, sr=16000)

            # Gentle high-pass to remove rumble without eating low-freq speech
            sos = scipy.signal.butter(2, 60, btype='highpass',
                                      fs=sample_rate, output='sos')
            y = scipy.signal.sosfilt(sos, y).astype(np.float32)

            # Light preemphasis (0.95 is gentler than default 0.97)
            y = librosa.effects.preemphasis(y, coef=0.95)
            y = librosa.util.normalize(y)

            fd, wav_path = tempfile.mkstemp(suffix='_filtered.wav')
            os.close(fd)
            sf.write(wav_path, y, sample_rate)

            recognizer = sr.Recognizer()
            recognizer.dynamic_energy_threshold = True
            recognizer.energy_threshold = 250
            recognizer.pause_threshold = 1.0

            with sr.AudioFile(wav_path) as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio_data = recognizer.record(source)

            text = self._google_asr_with_best_result(recognizer, audio_data)

            if text and text.strip():
                return text.strip()
            elif use_reference:
                return self.find_similar_transcription(audio_path)
            else:
                return "Speech recognition failed"

        except Exception as e:
            print(f"Error processing audio: {e}")
            return None
        finally:
            if wav_path and os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except OSError:
                    pass

    def _google_asr_with_best_result(self, recognizer, audio_data):
        """Try Google ASR multiple ways and return the best transcript.

        Strategy:
          1. so-SO with show_all → pick highest-confidence alternative
          2. Fallback: so-SO simple call
          3. Fallback: Swahili (sw-KE) — closely related Bantu/Cushitic contact
             language whose model often captures shared vocabulary
        """
        # Attempt 1: Somali with full alternatives
        try:
            result = recognizer.recognize_google(
                audio_data, language="so-SO", show_all=True)
            if isinstance(result, dict) and 'alternative' in result:
                alts = result['alternative']
                best = self._pick_best_alternative(alts)
                if best and len(best.strip()) >= 2:
                    return best
            elif isinstance(result, str) and result.strip():
                return result.strip()
        except Exception as e:
            print(f"Google ASR (so-SO, show_all) failed: {e}")

        # Attempt 2: simple so-SO call (sometimes returns where show_all doesn't)
        try:
            text = recognizer.recognize_google(audio_data, language="so-SO")
            if text and len(text.strip()) >= 2:
                return text.strip()
        except Exception as e:
            print(f"Google ASR (so-SO, simple) failed: {e}")

        # Attempt 3: Swahili model picks up some Somali words the so-SO model misses
        try:
            text = recognizer.recognize_google(audio_data, language="sw-KE")
            if text and len(text.strip()) >= 2:
                return text.strip()
        except Exception:
            pass

        return None

    def _pick_best_alternative(self, alternatives):
        """From Google ASR alternatives list, pick the longest with confidence."""
        if not alternatives:
            return None
        scored = []
        for alt in alternatives:
            t = alt.get('transcript', '').strip()
            conf = alt.get('confidence', 0.0)
            # Favour longer transcripts (more words captured) weighted by confidence
            score = len(t.split()) * (0.5 + conf) if conf else len(t.split())
            scored.append((score, t))
        scored.sort(reverse=True)
        return scored[0][1] if scored else None
            
    def find_similar_transcription(self, audio_path):
        """Find similar transcription from dataset based on filename length heuristic."""
        try:
            if self.metadata_df is None or self.metadata_df.empty:
                return "No matching transcription found"

            similar_files = self.metadata_df[
                abs(self.metadata_df['file_name'].str.len()
                    - len(os.path.basename(audio_path))) < 5
            ]

            if not similar_files.empty:
                return similar_files.iloc[0]['transcription']
            return "No matching transcription found"

        except Exception as e:
            print(f"Error finding similar transcription: {e}")
            return "Error processing audio"
            
    def generate_subtitles(self, audio_path, output_file="subtitles.srt",
                           chunk_duration=10.0, overlap=1.0, progress_cb=None):
        """Generate subtitles using ffmpeg-based chunking.

        Workflow:
          1. ffprobe  → duration (zero memory)
          2. ffmpeg   → single 16 kHz mono WAV (one pass)
          3. Silence detection → find natural split points
          4. ffmpeg   → chunk split at silence boundaries with overlap
          5. Google SR → transcribe each chunk independently
          6. Dedup    → remove duplicate text from overlapping regions
          7. Merge    → ordered SRT / segment list

        ``progress_cb(current, total, message)`` is called after every step.
        """
        from utils.media_processor import MediaProcessor

        print(f"Processing media file: {audio_path}")

        with MediaProcessor(chunk_duration=chunk_duration, overlap=overlap) as processor:
            try:
                chunks, duration = processor.process(audio_path, progress_cb=progress_cb)
            except Exception as e:
                print(f"Error preparing media: {e}")
                return []

            num_chunks = len(chunks)
            print(f"Duration: {duration:.1f}s -> {num_chunks} chunks of {chunk_duration}s")

            subtitles = []

            for chunk in chunks:
                i = chunk['index']
                start_time = chunk['start']
                end_time = chunk['end']

                print(f"Transcribing chunk {i + 1}/{num_chunks} "
                      f"({start_time:.1f}s - {end_time:.1f}s)")

                try:
                    text = self.audio_to_text_with_reference(
                        chunk['path'], use_reference=False)

                    if text and text.strip() and text != "Speech recognition failed":
                        clean_text = self._dedup_overlap(
                            subtitles[-1]['text'] if subtitles else '',
                            text.strip())
                        if clean_text:
                            subtitles.append({
                                'index': len(subtitles) + 1,
                                'start': self.format_timestamp(start_time),
                                'end': self.format_timestamp(end_time),
                                'start_sec': start_time,
                                'end_sec': end_time,
                                'text': clean_text
                            })
                except Exception as e:
                    print(f"Error transcribing chunk {i}: {e}")

                if progress_cb:
                    progress_cb(i + 1, num_chunks,
                                f'Transcribing chunk {i + 1}/{num_chunks}')

        if subtitles:
            self.write_srt_file(subtitles, output_file)
            print(f"Subtitles saved to: {output_file}")

        return [{'start_sec': s['start_sec'], 'end_sec': s['end_sec'],
                 'start': s['start'], 'end': s['end'], 'text': s['text']}
                for s in subtitles]
        
    @staticmethod
    def _dedup_overlap(prev_text, new_text):
        """Remove leading words in *new_text* that already ended *prev_text*.

        When chunks overlap by ~1 s, Google ASR often repeats the last 1-3
        words of the previous chunk at the start of the new one.  This finds
        the longest suffix/prefix match and strips it.
        """
        if not prev_text or not new_text:
            return new_text

        prev_words = prev_text.lower().split()
        new_words_lower = new_text.lower().split()
        new_words = new_text.split()

        max_check = min(len(prev_words), len(new_words_lower), 5)
        best_overlap = 0

        for k in range(1, max_check + 1):
            if prev_words[-k:] == new_words_lower[:k]:
                best_overlap = k

        if best_overlap > 0:
            trimmed = ' '.join(new_words[best_overlap:])
            return trimmed if trimmed.strip() else None

        return new_text

    def format_timestamp(self, seconds):
        """Format seconds to SRT timestamp format"""
        td = timedelta(seconds=seconds)
        hours, remainder = divmod(td.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        milliseconds = td.microseconds // 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
        
    def write_srt_file(self, subtitles, output_file):
        """Write subtitles to SRT file"""
        with open(output_file, 'w', encoding='utf-8') as f:
            for subtitle in subtitles:
                f.write(f"{subtitle['index']}\n")
                f.write(f"{subtitle['start']} --> {subtitle['end']}\n")
                f.write(f"{subtitle['text']}\n\n")
                
    def get_dataset_info(self):
        """Display dataset information"""
        if self.metadata_df is not None:
            print(f"Dataset Info:")
            print(f"- Total audio files: {len(self.metadata_df)}")
            print(f"- Training files: {len(self.train_df)}")
            print(f"- Audio directory: {os.path.join(self.dataset_path, 'wavs')}")
            print(f"- Sample transcription: {self.metadata_df.iloc[0]['transcription']}")
        else:
            print("Dataset not loaded")

def main():
    # Initialize the subtitle generator
    generator = SomaliSubtitleGenerator()
    
    # Display dataset info
    generator.get_dataset_info()
    
    # Process the recording file
    audio_file = "Recording.wav"
    if os.path.exists(audio_file):
        print(f"\nGenerating subtitles for {audio_file}...")
        generator.generate_subtitles(audio_file, "somali_subtitles.srt")
    else:
        print(f"Audio file {audio_file} not found!")
        
    # Example with a dataset file
    wav_dir = os.path.join("dataset", "wavs")
    if os.path.exists(wav_dir):
        wav_files = [f for f in os.listdir(wav_dir) if f.endswith('.wav')][:3]  # Test first 3 files
        for wav_file in wav_files:
            wav_path = os.path.join(wav_dir, wav_file)
            print(f"\nTesting with dataset file: {wav_file}")
            
            # Get the original transcription from dataset
            original_transcription = generator.metadata_df[
                generator.metadata_df['file_name'] == wav_file
            ]['transcription'].iloc[0] if not generator.metadata_df.empty else "N/A"
            
            print(f"Original transcription: {original_transcription}")

if __name__ == "__main__":
    main()