"""Reconhecimento de voz em uma thread separada da reprodução."""
import json
import queue
import threading
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

MODEL_PATH = Path(__file__).resolve().parent / 'vosk-model-small-pt-0.3'
LOG_PATH = Path(__file__).resolve().parent / 'conversas.jsonl'


class Transcricao:
    def __init__(self, emit):
        self.emit = emit
        self.blocks = queue.Queue(maxsize=100)
        self.finished = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def submit(self, samples):
        if not self.finished.is_set():
            try:
                self.blocks.put_nowait(samples.copy())
            except queue.Full:
                self.emit('transcription_warning', 'Transcrição atrasada: alguns trechos foram perdidos.')

    def stop(self):
        self.finished.set()

    def run(self):
        try:
            from vosk import Model, KaldiRecognizer
            # O Vosk no Windows pode falhar com caracteres acentuados no caminho absoluto.
            # app.py define o diretório atual como a pasta do aplicativo na inicialização.
            model = Model(MODEL_PATH.name)
            recognizer = KaldiRecognizer(model, 16000)
            self.emit('transcription_status', 'Legendas prontas. Aguardando fala na entrada selecionada...')
            while not self.finished.is_set() or not self.blocks.empty():
                try:
                    samples = self.blocks.get(timeout=0.2)
                except queue.Empty:
                    continue
                samples = resample_poly(samples, 160, 441)
                pcm = (np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes()
                if recognizer.AcceptWaveform(pcm):
                    self.save(json.loads(recognizer.Result()).get('text', ''))
                else:
                    partial = json.loads(recognizer.PartialResult()).get('partial', '')
                    if partial:
                        self.emit('subtitle', partial)
            self.save(json.loads(recognizer.FinalResult()).get('text', ''))
        except Exception as exc:
            self.emit('transcription_error', str(exc))

    def save(self, text):
        if not text.strip():
            return
        entry = {'horario': datetime.now().isoformat(timespec='seconds'), 'texto': text.strip()}
        with LOG_PATH.open('a', encoding='utf-8') as log:
            log.write(json.dumps(entry, ensure_ascii=False) + '\n')
        self.emit('transcript', entry)
