import queue
import threading
import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np
import noisereduce as nr
import sounddevice as sd
from scipy import signal
from transcricao import Transcricao, MODEL_PATH, LOG_PATH
from globo import Globo

RATE = 44100
BLOCK = 4096


class RadioApp:
    def __init__(self, root):
        self.root = root
        root.title('PX CONTROL // Centro de comunicações')
        root.geometry('1280x820')
        root.minsize(1050, 720)
        root.configure(background='#050d17')
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', background='#07121e', foreground='#d5eaf0', font=('Segoe UI', 10))
        style.configure('TFrame', background='#07121e')
        style.configure('Panel.TFrame', background='#0a1b29')
        style.configure('TLabel', background='#07121e', foreground='#d5eaf0')
        style.configure('Title.TLabel', background='#0a1b29', foreground='#5ce6d0', font=('Consolas', 11, 'bold'))
        style.configure('Muted.TLabel', background='#0a1b29', foreground='#7295a4', font=('Consolas', 9))
        style.configure('Info.TLabel', background='#0a1b29', foreground='#d5eaf0', font=('Consolas', 10, 'bold'))
        style.configure('TLabelframe', background='#07121e', foreground='#5ce6d0', bordercolor='#254756')
        style.configure('TLabelframe.Label', background='#07121e', foreground='#5ce6d0', font=('Consolas', 10, 'bold'))
        style.configure('TCheckbutton', background='#07121e', foreground='#d5eaf0')
        style.map('TCheckbutton', background=[('active', '#102b38')])
        style.configure('TButton', background='#123646', foreground='#a7f5e7', bordercolor='#267286', padding=6)
        style.map('TButton', background=[('active', '#205469'), ('disabled', '#14212a')], foreground=[('disabled', '#586c74')])
        style.configure('TEntry', fieldbackground='#102b38', foreground='#e4f7f8', insertcolor='white')
        style.configure('TCombobox', fieldbackground='#102b38', foreground='#e4f7f8', background='#123646', arrowcolor='#5ce6d0')
        style.map('TCombobox', fieldbackground=[('readonly', '#102b38')], foreground=[('readonly', '#e4f7f8')])
        self.events = queue.Queue(maxsize=8)
        self.stop_event = threading.Event()
        self.capture_event = threading.Event()
        self.worker = None
        self.transcriber = None
        self.transcription_threads = []
        self.log_window = None
        self.devices = []
        self.enabled = tk.BooleanVar(value=True)
        self.voice = tk.BooleanVar(value=True)
        self.subtitles_enabled = tk.BooleanVar(value=False)
        self.subtitle = tk.StringVar(value='Legendas desativadas.')
        self.strength = tk.DoubleVar(value=0.75)
        self.gain = tk.DoubleVar(value=1.0)
        self.status = tk.StringVar(value='Selecione os dispositivos e clique em Iniciar.')

        layout = ttk.Frame(root, padding=12)
        layout.pack(fill='both', expand=True)
        bottom = ttk.Frame(layout)
        bottom.pack(side='bottom', fill='x', pady=(10, 0))
        buttons = ttk.Frame(bottom)
        buttons.pack(side='left', anchor='n', padx=(0, 12))
        self.start_button = ttk.Button(buttons, text='Iniciar', command=self.start)
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(buttons, text='Parar', command=self.stop, state='disabled')
        self.stop_button.pack(side='left', padx=8)
        alphabet = ttk.Frame(bottom, style='Panel.TFrame', padding=10)
        alphabet.pack(side='left', fill='x', expand=True)
        ttk.Label(alphabet, text='ALFABETO FONÉTICO', style='Title.TLabel').pack(anchor='w', pady=(0, 6))
        words = ['Alfa', 'Bravo', 'Charlie', 'Delta', 'Echo', 'Foxtrot', 'Golf', 'Hotel', 'India', 'Juliett', 'Kilo', 'Lima', 'Mike', 'November', 'Oscar', 'Papa', 'Quebec', 'Romeo', 'Sierra', 'Tango', 'Uniform', 'Victor', 'Whiskey', 'X-ray', 'Yankee', 'Zulu']
        letters = ttk.Frame(alphabet, style='Panel.TFrame')
        letters.pack(fill='x')
        for i, word in enumerate(words):
            row, column = divmod(i, 9)
            letters.columnconfigure(column, weight=1)
            ttk.Label(letters, text=f'{chr(65+i)} {word}', style='Muted.TLabel').grid(row=row, column=column, sticky='w', padx=(0, 6), pady=2)
        main = ttk.Frame(layout, padding=(0, 0, 10, 0))
        main.pack(side='left', fill='both', expand=True)
        right = ttk.Frame(layout, width=385)
        right.pack(side='right', fill='both')
        right.pack_propagate(False)
        ttk.Button(right, text='📖  LOG DE CONVERSAS', command=self.open_log).pack(anchor='e', pady=(0, 8))
        self.globo = Globo(right)
        self.globo.pack(fill='both', expand=True)
        heading = ttk.Frame(main)
        heading.pack(fill='x')
        ttk.Label(heading, text='PX  /  CONTROL', foreground='#67ead5', font=('Consolas', 20, 'bold')).pack(side='left')
        ttk.Label(main, text='CENTRO DE COMUNICAÇÕES  //  SISTEMA DE ÁUDIO', foreground='#739aa8', font=('Consolas', 9)).pack(anchor='w', pady=(0, 12))
        devices = ttk.LabelFrame(main, text='Dispositivos de áudio', padding=10)
        devices.pack(fill='x')
        devices.columnconfigure(1, weight=1)
        ttk.Label(devices, text='Entrada do rádio').grid(row=0, column=0, sticky='w', padx=(0, 10))
        self.input_box = ttk.Combobox(devices, state='readonly')
        self.input_box.grid(row=0, column=1, sticky='ew', pady=3)
        ttk.Label(devices, text='Saída do computador').grid(row=1, column=0, sticky='w')
        self.output_box = ttk.Combobox(devices, state='readonly')
        self.output_box.grid(row=1, column=1, sticky='ew', pady=3)
        self.refresh_button = ttk.Button(devices, text='Atualizar lista', command=self.refresh)
        self.refresh_button.grid(row=0, column=2, padx=(10, 0))
        self.scan_button = ttk.Button(devices, text='Procurar', command=self.start_scan)
        self.scan_button.grid(row=1, column=2, padx=(10, 0))

        controls = ttk.LabelFrame(main, text='Melhorias', padding=10)
        controls.pack(fill='x', pady=10)
        ttk.Checkbutton(controls, text='Redução de ruído', variable=self.enabled).grid(row=0, column=0, sticky='w')
        ttk.Checkbutton(controls, text='Realçar voz (300–3000 Hz)', variable=self.voice).grid(row=0, column=1, sticky='w', padx=20)
        ttk.Label(controls, text='Intensidade da redução').grid(row=1, column=0, sticky='w', pady=(10, 0))
        ttk.Scale(controls, from_=0, to=1, variable=self.strength).grid(row=2, column=0, sticky='ew')
        ttk.Label(controls, text='Volume de saída').grid(row=1, column=1, sticky='w', padx=20, pady=(10, 0))
        ttk.Scale(controls, from_=0, to=2, variable=self.gain).grid(row=2, column=1, sticky='ew', padx=20)
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)
        self.capture_button = ttk.Button(controls, text='Capturar ruído (2 s)', command=self.capture, state='disabled')
        self.capture_button.grid(row=3, column=0, sticky='w', pady=(12, 0))
        ttk.Label(controls, text='Capture somente o chiado, sem voz.').grid(row=3, column=1, sticky='w', padx=20, pady=(12, 0))
        ttk.Checkbutton(controls, text='Ativar legendas', variable=self.subtitles_enabled,
                        command=self.toggle_subtitles).grid(row=4, column=0, sticky='w', pady=(10, 0))

        graph = ttk.LabelFrame(main, text='Onda sonora de saída', padding=8)
        graph.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(graph, background='#101a25', highlightthickness=0, height=160)
        self.canvas.pack(fill='both', expand=True)
        ttk.Label(main, textvariable=self.subtitle, wraplength=800, anchor='center',
                  font=('Segoe UI', 12), padding=8).pack(fill='x')
        ttk.Label(main, textvariable=self.status, wraplength=800).pack(anchor='w')
        self.refresh()
        self.scan_running = False
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.after(80, self.poll)

    def refresh(self):
        try:
            self.devices = sd.query_devices()
            inputs = [(i, d) for i, d in enumerate(self.devices) if d['max_input_channels'] > 0]
            outputs = [(i, d) for i, d in enumerate(self.devices) if d['max_output_channels'] > 0]
            self.input_ids = [i for i, _ in inputs]
            self.output_ids = [i for i, _ in outputs]
            self.input_box['values'] = [f"{i}: {d['name']}" for i, d in inputs]
            self.output_box['values'] = [f"{i}: {d['name']}" for i, d in outputs]
            defaults = sd.default.device
            if inputs:
                self.input_box.current(self.input_ids.index(defaults[0]) if defaults[0] in self.input_ids else 0)
            if outputs:
                self.output_box.current(self.output_ids.index(defaults[1]) if defaults[1] in self.output_ids else 0)
        except Exception as exc:
            messagebox.showerror('Áudio', f'Não foi possível listar dispositivos: {exc}')

    def start_scan(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo('Áudio ativo', 'Pare o áudio antes de procurar entradas.')
            return
        self.stop_event.clear()
        self.scan_running = True
        self.refresh_button.config(state='disabled')
        self.scan_button.config(state='disabled')
        threading.Thread(target=self.scan_inputs, daemon=True).start()

    def scan_inputs(self):
        scores = []
        self.emit('scan', 'Procurando o rádio nas entradas de áudio...')
        for device_id in list(self.input_ids):
            if self.stop_event.is_set():
                return
            try:
                sd.check_input_settings(device=device_id, channels=1, samplerate=RATE, dtype='float32')
                with sd.InputStream(device=device_id, channels=1, samplerate=RATE,
                                    dtype='float32', blocksize=BLOCK) as stream:
                    blocks = []
                    for _ in range((RATE * 4 + BLOCK - 1) // BLOCK):
                        if self.stop_event.is_set():
                            return
                        data, _ = stream.read(BLOCK)
                        blocks.append(data[:, 0].copy())
                    samples = np.concatenate(blocks)[:RATE * 4]
                    scores.append((float(np.sqrt(np.mean(samples ** 2))), device_id))
            except Exception:
                continue
        self.emit('scan_done', max(scores, default=None))

    def show_toast(self, text):
        toast = tk.Toplevel(self.root)
        toast.title('Detecção de entrada')
        toast.transient(self.root)
        toast.resizable(False, False)
        ttk.Label(toast, text=text, padding=16, wraplength=420).pack()
        ttk.Button(toast, text='Fechar', command=toast.destroy).pack(pady=(0, 12))
        toast.after(12000, lambda: toast.destroy() if toast.winfo_exists() else None)

    def start(self):
        if self.scan_running:
            messagebox.showinfo('Detecção em andamento', 'Aguarde a verificação das entradas terminar.')
            return
        if self.input_box.current() < 0 or self.output_box.current() < 0:
            messagebox.showerror('Áudio', 'Selecione uma entrada e uma saída de áudio.')
            return
        inp = self.input_ids[self.input_box.current()]
        out = self.output_ids[self.output_box.current()]
        try:
            sd.check_input_settings(device=inp, channels=1, samplerate=RATE, dtype='float32')
            sd.check_output_settings(device=out, channels=1, samplerate=RATE, dtype='float32')
        except Exception as exc:
            messagebox.showerror('Dispositivos incompatíveis', f'Não foi possível usar os dispositivos em 44100 Hz, mono: {exc}')
            return
        self.stop_event.clear()
        self.capture_event.clear()
        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        self.capture_button.config(state='normal')
        self.input_box.config(state='disabled')
        self.output_box.config(state='disabled')
        self.status.set('Iniciando áudio...')
        self.settings = (self.enabled.get(), self.voice.get(), self.strength.get(), self.gain.get())
        self.worker = threading.Thread(target=self.audio_loop, args=(inp, out), daemon=True)
        self.worker.start()
        if self.subtitles_enabled.get():
            self.start_transcription()

    def toggle_subtitles(self):
        if self.subtitles_enabled.get():
            if not MODEL_PATH.is_dir():
                self.subtitles_enabled.set(False)
                messagebox.showerror('Modelo não encontrado',
                                     'Baixe e extraia o modelo de português do Vosk conforme as instruções do README.md.')
                return
            if self.worker and self.worker.is_alive() and not self.stop_event.is_set():
                self.start_transcription()
            else:
                self.subtitle.set('Legendas ativadas. Inicie o áudio para transcrever.')
        else:
            self.stop_transcription()
            self.subtitle.set('Legendas desativadas.')

    def start_transcription(self):
        if self.transcriber is None:
            self.subtitle.set('Carregando modelo de voz...')
            self.transcriber = Transcricao(self.emit)
            self.transcription_threads.append(self.transcriber.thread)

    def stop_transcription(self):
        transcriber, self.transcriber = self.transcriber, None
        if transcriber:
            transcriber.stop()

    def open_log(self):
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.lift()
            return
        self.log_window = tk.Toplevel(self.root)
        self.log_window.title('Log de conversas')
        self.log_window.geometry('650x450')
        frame = ttk.Frame(self.log_window, padding=10)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Conversas reconhecidas — mais recentes primeiro').pack(anchor='w')
        self.log_text = tk.Text(frame, wrap='word', state='disabled')
        self.log_text.pack(fill='both', expand=True, pady=8)
        try:
            if LOG_PATH.exists():
                for line in LOG_PATH.read_text(encoding='utf-8').splitlines():
                    try:
                        self.add_log_entry(json.loads(line))
                    except (ValueError, KeyError, TypeError):
                        continue
        except OSError as exc:
            messagebox.showerror('Erro ao abrir log', str(exc), parent=self.log_window)

    def add_log_entry(self, entry):
        if self.log_window and self.log_window.winfo_exists():
            self.log_text.config(state='normal')
            self.log_text.insert('1.0', f"{entry['horario'].replace('T', ' ')}  —  {entry['texto']}\n\n")
            self.log_text.config(state='disabled')

    def emit(self, kind, value):
        try:
            self.events.put_nowait((kind, value))
        except queue.Full:
            if kind != 'wave':
                self.events.put((kind, value))

    def audio_loop(self, inp, out):
        noise = None
        collected = []
        remaining = 0
        sos = signal.butter(4, [300, 3000], btype='bandpass', fs=RATE, output='sos')
        zi = np.zeros((len(sos), 2))
        was_voice = False
        try:
            with sd.Stream(device=(inp, out), samplerate=RATE, blocksize=BLOCK,
                           channels=1, dtype='float32', latency='high') as stream:
                self.emit('status', 'Áudio ativo. Capture o chiado sem ninguém falando para melhorar a redução.')
                while not self.stop_event.is_set():
                    data, overflow = stream.read(BLOCK)
                    samples = data[:, 0].copy()
                    # O reconhecimento recebe a entrada original: o volume de saída,
                    # o filtro de voz e a redução não devem silenciar a legenda.
                    transcriber = self.transcriber
                    if transcriber:
                        transcriber.submit(samples)
                    if self.capture_event.is_set():
                        self.capture_event.clear()
                        collected = []
                        remaining = RATE * 2
                        self.emit('status', 'Capturando chiado por 2 segundos...')
                    if remaining > 0:
                        collected.append(samples.copy())
                        remaining -= len(samples)
                        if remaining <= 0:
                            noise = np.concatenate(collected)[:RATE * 2]
                            self.emit('status', 'Amostra de ruído capturada. Pode ouvir as conversas.')
                    enabled, voice, strength, gain = self.settings
                    if enabled and noise is not None and strength > 0:
                        samples = nr.reduce_noise(y=samples, sr=RATE, y_noise=noise,
                                                  stationary=True, prop_decrease=strength,
                                                  n_fft=512, hop_length=128)
                    if voice:
                        if not was_voice:
                            zi = np.zeros((len(sos), 2))
                        samples, zi = signal.sosfilt(sos, samples, zi=zi)
                    was_voice = voice
                    samples = np.clip(samples * gain, -1, 1).astype(np.float32)
                    underflow = stream.write(samples.reshape(-1, 1))
                    self.emit('wave', samples[::max(1, len(samples)//400)])
                    if overflow or underflow:
                        self.emit('status', 'Áudio ativo; houve falha de tempo. Feche outros programas ou reduza a carga do computador.')
        except Exception as exc:
            self.emit('error', str(exc))
        finally:
            self.emit('stopped', None)

    def capture(self):
        self.capture_event.set()

    def stop(self):
        self.stop_event.set()
        self.stop_transcription()
        if self.subtitles_enabled.get():
            self.subtitle.set('Áudio parado. Legendas serão retomadas ao iniciar.')
        self.stop_button.config(state='disabled')
        self.status.set('Parando áudio...')

    def poll(self):
        self.settings = (self.enabled.get(), self.voice.get(), self.strength.get(), self.gain.get())
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'wave':
                    self.draw(value)
                elif kind == 'scan':
                    self.status.set(value)
                elif kind == 'scan_done':
                    self.scan_running = False
                    self.refresh_button.config(state='normal')
                    self.scan_button.config(state='normal')
                    if value and value[0] > 0.001:
                        level, device_id = value
                        if device_id in self.input_ids:
                            self.input_box.current(self.input_ids.index(device_id))
                        name = self.devices[device_id]['name']
                        self.status.set('Verificação concluída. Confirme a entrada selecionada.')
                        self.show_toast(f'Possível entrada do rádio: {device_id}: {name}\n\nFoi escolhida a entrada com sinal mais forte. Confirme ouvindo o rádio; outros sons também podem ser detectados.')
                    else:
                        self.status.set('Nenhum sinal significativo detectado. Selecione a entrada manualmente.')
                        self.show_toast('Nenhum sinal significativo foi detectado. Confira a ligação e o volume do rádio e selecione a entrada manualmente.')
                elif kind == 'status':
                    self.status.set(value)
                elif kind == 'subtitle':
                    if self.subtitles_enabled.get() and self.transcriber:
                        self.subtitle.set(value)
                elif kind == 'transcript':
                    self.add_log_entry(value)
                    if self.subtitles_enabled.get() and self.transcriber:
                        self.subtitle.set(value['texto'])
                elif kind == 'transcription_status':
                    if self.subtitles_enabled.get() and self.transcriber:
                        self.subtitle.set(value)
                elif kind == 'transcription_warning':
                    self.status.set(value)
                elif kind == 'transcription_error':
                    self.stop_transcription()
                    self.subtitles_enabled.set(False)
                    self.subtitle.set('Legendas desativadas devido a erro.')
                    messagebox.showerror('Erro na transcrição', value)
                elif kind == 'error':
                    self.status.set('Erro no áudio.')
                    messagebox.showerror('Erro no áudio', value)
                elif kind == 'stopped':
                    self.stop_transcription()
                    self.start_button.config(state='normal')
                    self.stop_button.config(state='disabled')
                    self.capture_button.config(state='disabled')
                    self.input_box.config(state='readonly')
                    self.output_box.config(state='readonly')
                    if self.status.get() != 'Erro no áudio.':
                        self.status.set('Áudio parado.')
        except queue.Empty:
            pass
        self.root.after(80, self.poll)

    def draw(self, samples):
        canvas = self.canvas
        width, height = max(canvas.winfo_width(), 2), max(canvas.winfo_height(), 2)
        canvas.delete('all')
        canvas.create_line(0, height / 2, width, height / 2, fill='#34495b')
        points = []
        for i, sample in enumerate(samples):
            points.extend((i * width / max(len(samples) - 1, 1), height / 2 - float(sample) * height * 0.48))
        if len(points) >= 4:
            canvas.create_line(*points, fill='#4de0bb', width=1)

    def close(self):
        self.stop_event.set()
        self.stop_transcription()
        self.status.set('Finalizando e salvando transcrições...')
        self.root.protocol('WM_DELETE_WINDOW', lambda: None)
        self.finish_close()

    def finish_close(self):
        if any(thread.is_alive() for thread in self.transcription_threads):
            self.root.after(100, self.finish_close)
        else:
            self.root.destroy()


if __name__ == '__main__':
    os.chdir(Path(__file__).resolve().parent)
    root = tk.Tk()
    RadioApp(root)
    root.mainloop()
