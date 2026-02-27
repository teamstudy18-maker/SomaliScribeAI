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
        """Convert audio to text using the dataset as reference."""
        import tempfile
        wav_path = None
        try:
            import librosa
            import scipy.signal
            import soundfile as sf

            y, sample_rate = librosa.load(audio_path, sr=16000)

            sos = scipy.signal.butter(5, 80, btype='highpass',
                                      fs=sample_rate, output='sos')
            y = scipy.signal.sosfilt(sos, y).astype(np.float32)
            y = librosa.effects.preemphasis(y)
            y = librosa.util.normalize(y)

            fd, wav_path = tempfile.mkstemp(suffix='_filtered.wav')
            os.close(fd)
            sf.write(wav_path, y, sample_rate)

            recognizer = sr.Recognizer()
            recognizer.dynamic_energy_threshold = True
            recognizer.energy_threshold = 300

            with sr.AudioFile(wav_path) as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio_data = recognizer.record(source)

            text = None

            try:
                text = recognizer.recognize_google(
                    audio_data, language="so-SO", show_all=True)
                if isinstance(text, dict) and 'alternative' in text:
                    text = text['alternative'][0]['transcript']
                elif isinstance(text, list):
                    text = text[0]['transcript']
                else:
                    text = str(text)
            except Exception as e:
                print(f"Google Speech Recognition failed: {e}")

            if not text or len(text.strip()) < 3:
                try:
                    recognizer.energy_threshold = 200
                    text = recognizer.recognize_google(
                        audio_data, language="so-SO")
                except Exception as e:
                    print(f"Second attempt failed: {e}")
                    text = None

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
                           chunk_duration=4.0, progress_cb=None):
        """Generate subtitles using ffmpeg-based chunking.

        Workflow:
          1. ffprobe  → duration (zero memory)
          2. ffmpeg   → single 16 kHz mono WAV (one pass)
          3. ffmpeg   → byte-accurate chunk split (O(1) seek per chunk)
          4. Google SR → transcribe each chunk independently
          5. Merge    → ordered SRT / segment list

        ``progress_cb(current, total, message)`` is called after every step.
        """
        from utils.media_processor import MediaProcessor

        print(f"Processing media file: {audio_path}")

        with MediaProcessor(chunk_duration=chunk_duration) as processor:
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
                        subtitles.append({
                            'index': len(subtitles) + 1,
                            'start': self.format_timestamp(start_time),
                            'end': self.format_timestamp(end_time),
                            'start_sec': start_time,
                            'end_sec': end_time,
                            'text': text.strip()
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