import queue
import threading
import json
import logging
import os
import re
import webbrowser
from collections import deque
from pathlib import Path
from urllib.parse import urlencode
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np
import noisereduce as nr
import sounddevice as sd
from scipy import signal
from transcricao import Transcricao, MODELOS, LOG_PATH
from globo import Globo
from contatos import buscar_contato, buscar_wrl_publico, registrar_busca, atualizar_nome_contato, nome_no_historico, LOG_CONTATOS

RATE = 44100
BLOCK = 4096
MAX_REPLAY_SECONDS = 60


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
        style.configure('TRadiobutton', background='#07121e', foreground='#d5eaf0')
        style.map('TRadiobutton', background=[('active', '#102b38')], foreground=[('disabled', '#71909c')])
        style.configure('TButton', background='#123646', foreground='#a7f5e7', bordercolor='#267286', padding=6)
        style.map('TButton', background=[('active', '#205469'), ('disabled', '#14212a')], foreground=[('disabled', '#586c74')])
        style.configure('TEntry', fieldbackground='#102b38', foreground='#e4f7f8', insertcolor='white')
        style.configure('TCombobox', fieldbackground='#102b38', foreground='#e4f7f8', background='#123646', arrowcolor='#5ce6d0')
        style.map('TCombobox', fieldbackground=[('readonly', '#102b38')], foreground=[('readonly', '#e4f7f8')])
        style.configure('Busca.Treeview', background='#f1f4f5', fieldbackground='#f1f4f5', foreground='#17232a', rowheight=26)
        style.map('Busca.Treeview', background=[('selected', '#286678')], foreground=[('selected', '#ffffff')])
        style.configure('Busca.Treeview.Heading', background='#cbd8dc', foreground='#17232a', font=('Segoe UI', 10, 'bold'))
        self.events = queue.Queue(maxsize=8)
        self.stop_event = threading.Event()
        self.capture_event = threading.Event()
        self.replay_lock = threading.Lock()
        self.audio_history = deque(maxlen=(RATE * MAX_REPLAY_SECONDS + BLOCK - 1) // BLOCK)
        self.pending_replay = None
        self.worker = None
        self.transcriber = None
        self.fullscreen_window = None
        self.fullscreen_canvas = None
        self.fullscreen_globe = None
        self.last_wave = np.zeros(2)
        self.transcription_generation = 0
        self.transcription_threads = []
        self.log_window = None
        self.devices = []
        self.enabled = tk.BooleanVar(value=True)
        self.voice = tk.BooleanVar(value=True)
        self.subtitles_enabled = tk.BooleanVar(value=False)
        self.subtitle_language = tk.StringVar(value='Português')
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
        self.replay_seconds = tk.StringVar(value='5')
        self.replay_button = ttk.Button(buttons, text='Replay', width=7, command=self.replay, state='disabled')
        self.replay_button.pack(side='left')
        ttk.Entry(buttons, width=4, textvariable=self.replay_seconds).pack(side='left', padx=(4, 2))
        ttk.Label(buttons, text='s').pack(side='left')
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
        right_buttons = ttk.Frame(right)
        right_buttons.pack(fill='x', pady=(0, 8))
        ttk.Button(right_buttons, text='📖  LOG DE CONVERSAS', command=self.open_log).pack(side='right')
        ttk.Button(right_buttons, text='⛶ TELA CHEIA', command=self.open_fullscreen).pack(side='left')
        self.globo = Globo(right)
        self.globo.pack(fill='both', expand=True)
        heading = ttk.Frame(main)
        heading.pack(fill='x')
        ttk.Label(heading, text='PX  /  CONTROL', foreground='#67ead5', font=('Consolas', 20, 'bold')).pack(side='left')
        lookup = ttk.Frame(main)
        lookup.pack(fill='x', pady=(0, 12))
        ttk.Label(lookup, text='SISTEMA DE ÁUDIO', foreground='#739aa8', font=('Consolas', 9)).pack(side='left')
        ttk.Button(lookup, text='Log', command=self.open_contact_log).pack(side='right', padx=(5, 0))
        self.wrl_button = ttk.Button(lookup, text='WRL', command=lambda: self.start_contact_search('WRL'))
        self.wrl_button.pack(side='right', padx=(5, 0))
        self.lookup_button = ttk.Button(lookup, text='HamDB', command=lambda: self.start_contact_search('HamDB'))
        self.lookup_button.pack(side='right', padx=(5, 0))
        ttk.Button(lookup, text='Google', command=self.search_google).pack(side='right', padx=(5, 0))
        self.callsign_text = tk.StringVar()
        self.callsign_text.trace_add('write', self.uppercase_callsign)
        self.callsign = ttk.Entry(lookup, width=17, textvariable=self.callsign_text)
        self.callsign.pack(side='right')
        self.callsign.bind('<Return>', self.search_google_from_key)
        self.callsign.bind('<Tab>', self.search_google_from_key)
        ttk.Label(lookup, text='Prefixo / indicativo', foreground='#739aa8').pack(side='right', padx=(5, 6))
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

        controls = ttk.LabelFrame(main, text='Melhorias', padding=6)
        controls.pack(fill='x', pady=5)
        ttk.Checkbutton(controls, text='Redução de ruído', variable=self.enabled).grid(row=0, column=0, sticky='w')
        ttk.Checkbutton(controls, text='Realçar voz (300–3000 Hz)', variable=self.voice).grid(row=0, column=1, sticky='w', padx=20)
        ttk.Label(controls, text='Intensidade da redução').grid(row=1, column=0, sticky='w', pady=(4, 0))
        ttk.Scale(controls, from_=0, to=1, variable=self.strength).grid(row=2, column=0, sticky='ew')
        ttk.Label(controls, text='Volume de saída').grid(row=1, column=1, sticky='w', padx=20, pady=(4, 0))
        ttk.Scale(controls, from_=0, to=2, variable=self.gain).grid(row=2, column=1, sticky='ew', padx=20)
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)
        self.capture_button = ttk.Button(controls, text='Capturar ruído (2 s)', command=self.capture, state='disabled')
        self.capture_button.grid(row=3, column=0, sticky='w', pady=(4, 0))
        ttk.Label(controls, text='Capture somente o chiado, sem voz.').grid(row=3, column=1, sticky='w', padx=20, pady=(4, 0))
        ttk.Checkbutton(controls, text='Ativar legendas', variable=self.subtitles_enabled,
                        command=self.toggle_subtitles).grid(row=4, column=0, sticky='w', pady=(4, 0))
        languages = ttk.Frame(controls)
        languages.grid(row=5, column=0, columnspan=2, sticky='w', pady=(4, 0))
        self.language_buttons = []
        for language in MODELOS:
            button = ttk.Radiobutton(languages, text=language, value=language, variable=self.subtitle_language)
            button.pack(side='left', padx=(0, 12))
            self.language_buttons.append(button)

        # Reserve espaço para a legenda antes de deixar o gráfico ocupar o restante.
        ttk.Label(main, textvariable=self.status, wraplength=700).pack(side='bottom', anchor='w', pady=(5, 0))
        subtitle_panel = tk.Frame(main, background='#000000', highlightbackground='#267286', highlightthickness=1)
        subtitle_panel.pack(side='bottom', fill='x', pady=(4, 0))
        subtitle_label = tk.Label(subtitle_panel, textvariable=self.subtitle, background='#000000',
                                  foreground='#ffffff', font=('Segoe UI', 10, 'bold'),
                                  anchor='center', justify='center', height=2, wraplength=600,
                                  padx=8, pady=2)
        subtitle_label.pack(fill='both', expand=True)
        subtitle_label.bind('<Configure>', lambda event: subtitle_label.configure(wraplength=max(100, event.width - 30)))

        graph = ttk.LabelFrame(main, text='Onda sonora de saída', padding=8)
        graph.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(graph, background='#101a25', highlightthickness=0, height=160)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda event: self.draw(np.zeros(2)))
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
        self.audio_history.clear()
        self.pending_replay = None
        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        self.capture_button.config(state='normal')
        self.replay_button.config(state='normal')
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
            idioma = self.subtitle_language.get()
            model_path = MODELOS[idioma]
            if not model_path.is_dir():
                self.subtitles_enabled.set(False)
                messagebox.showerror('Modelo não encontrado',
                                     f'Baixe e extraia o modelo de {idioma}:\n{model_path.name}\n\nConsulte as instruções do README.md.')
                return
            for button in self.language_buttons:
                button.config(state='disabled')
            if self.worker and self.worker.is_alive() and not self.stop_event.is_set():
                self.start_transcription()
            else:
                self.subtitle.set('Legendas ativadas. Inicie o áudio para transcrever.')
        else:
            self.stop_transcription()
            for button in self.language_buttons:
                button.config(state='normal')
            self.subtitle.set('Legendas desativadas.')

    def start_transcription(self):
        if self.transcriber is None:
            self.subtitle.set('Carregando modelo de voz...')
            self.transcription_generation += 1
            generation = self.transcription_generation
            def emit_transcription(kind, value):
                if kind == 'transcript':
                    self.emit(kind, value)
                else:
                    self.emit('transcription_event', (generation, kind, value))
            self.transcriber = Transcricao(emit_transcription, self.subtitle_language.get())
            self.transcription_threads.append(self.transcriber.thread)

    def stop_transcription(self):
        transcriber, self.transcriber = self.transcriber, None
        self.transcription_generation += 1
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

    def uppercase_callsign(self, *_):
        value = self.callsign_text.get()
        upper = value.upper()
        if value != upper:
            cursor = self.callsign.index('insert') if hasattr(self, 'callsign') else len(upper)
            self.callsign_text.set(upper)
            if hasattr(self, 'callsign'):
                self.callsign.icursor(cursor)

    def start_contact_search(self, fonte):
        if 'disabled' in self.lookup_button.state():
            return
        if fonte not in ('WRL', 'HamDB'):
            raise ValueError('Fonte de pesquisa inválida.')
        prefixo = self.callsign.get().strip()
        if not prefixo:
            messagebox.showinfo('Busca de contato', 'Digite o indicativo completo para pesquisar.')
            return
        self.show_known_name(prefixo)
        self.lookup_button.config(state='disabled')
        self.wrl_button.config(state='disabled')
        self.status.set(f'Consultando {prefixo.upper()} em {fonte}...')
        def worker():
            try:
                contact = buscar_wrl_publico(prefixo) if fonte == 'WRL' else buscar_contato(prefixo)
                warning = None
                try:
                    registrar_busca(prefixo, contact, fonte)
                except OSError as exc:
                    warning = str(exc)
                self.emit('contact_result', (contact, warning, fonte))
            except Exception as exc:
                self.emit('contact_error', (fonte, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def search_google(self, query=None):
        if query is None:
            query = self.callsign.get()
        if not query.strip():
            messagebox.showinfo('Busca no Google', 'Digite um texto para pesquisar.')
            return
        url = 'https://www.google.com/search?' + urlencode({'q': query})
        try:
            if not webbrowser.open(url):
                raise OSError('Não foi possível abrir o navegador padrão.')
            self.status.set('Pesquisa aberta no Google. O resumo de IA depende da disponibilidade do Google.')
        except Exception as exc:
            messagebox.showerror('Busca no Google', str(exc))

    def search_google_from_key(self, _event):
        query = self.callsign.get()
        if not query.strip() or not self.show_known_name(query):
            self.search_google(query)
        return 'break'

    def show_known_name(self, prefixo):
        try:
            nome = nome_no_historico(prefixo)
        except OSError as exc:
            logging.warning('Não foi possível consultar o histórico: %s', exc)
            return False
        if not nome:
            return False
        window = tk.Toplevel(self.root)
        window.title('Nome encontrado no histórico')
        window.transient(self.root)
        window.geometry('460x160')
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text=f'{prefixo.strip().upper()} — {nome}',
                  font=('Segoe UI', 15, 'bold'), wraplength=420).pack(anchor='w')
        ttk.Label(frame, text='Nome salvo anteriormente no histórico.', foreground='#739aa8').pack(anchor='w', pady=(8, 0))
        buttons = ttk.Frame(frame)
        buttons.pack(anchor='e', pady=(8, 0))
        ttk.Button(buttons, text='Fechar', command=window.destroy).pack(side='left', padx=(0, 8))
        def abrir_google():
            window.destroy()
            self.search_google(prefixo)
        ttk.Button(buttons, text='Google', command=abrir_google).pack(side='left')
        return True

    def show_contact(self, contact):
        window = tk.Toplevel(self.root)
        window.title(f"Contato — {contact['prefixo']}")
        window.geometry('700x480')
        window.transient(self.root)
        frame = ttk.Frame(window, padding=24)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='PERFIL DO CONTATO', foreground='#5ce6d0', font=('Consolas', 18, 'bold')).pack(anchor='w', pady=(0, 16))
        for label, key in [('Indicativo', 'prefixo'), ('Nome', 'nome'), ('Região', 'regiao'),
                           ('País', 'pais'), ('Localizador', 'grid'), ('Classe', 'classe'), ('Validade', 'validade')]:
            row = ttk.Frame(frame)
            row.pack(fill='x', pady=4)
            ttk.Label(row, text=label.upper(), width=15, foreground='#739aa8').pack(side='left')
            ttk.Label(row, text=str(contact[key]), wraplength=440).pack(side='left', fill='x', expand=True)
        if contact.get('horario_contato'):
            ttk.Label(frame, text=f"Contato registrado em: {contact['horario_contato']} (UTC)", foreground='#739aa8').pack(anchor='w', pady=(6, 0))
        ttk.Label(frame, text=f"Fonte: {contact.get('fonte', 'HamDB')} • dados sujeitos a atualização", foreground='#739aa8').pack(anchor='w', pady=(20, 0))

    def open_contact_log(self):
        window = tk.Toplevel(self.root)
        window.title('Log das buscas')
        window.geometry('950x480')
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='LOG DE BUSCAS  /  MAIS RECENTES PRIMEIRO', foreground='#5ce6d0', font=('Consolas', 12, 'bold')).pack(anchor='w', pady=(0, 10))
        columns = ('prefixo', 'nome', 'horario', 'regiao', 'pais', 'fonte')
        tree = ttk.Treeview(frame, columns=columns, show='headings', style='Busca.Treeview')
        for key, label, width in [('prefixo', 'Prefixo', 100), ('nome', 'Nome', 180), ('horario', 'Horário', 150), ('regiao', 'Região', 180), ('pais', 'País', 130), ('fonte', 'Fonte', 140)]:
            tree.heading(key, text=label)
            tree.column(key, width=width, minwidth=70)
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        editor = ttk.Frame(frame)
        editor.pack(side='bottom', fill='x', pady=(8, 0))
        ttk.Label(editor, text='Nome do contato selecionado:').pack(side='left', padx=(0, 8))
        nome = tk.StringVar()
        campo_nome = ttk.Entry(editor, textvariable=nome, state='disabled')
        campo_nome.pack(side='left', fill='x', expand=True)
        ttk.Label(editor, text='Salvo automaticamente', foreground='#739aa8').pack(side='left', padx=(8, 0))
        tree.pack(fill='both', expand=True)
        registros = {}
        selecionando = False
        try:
            if LOG_CONTATOS.exists():
                lines = LOG_CONTATOS.read_text(encoding='utf-8').splitlines()
                for indice in reversed(range(len(lines))):
                    line = lines[indice]
                    try:
                        entry = json.loads(line)
                        item = tree.insert('', 'end', values=[str(entry.get(key, '')).replace('T', ' ') if key == 'horario' else entry.get(key, '') for key in columns])
                        registros[item] = [indice, line]
                    except (ValueError, TypeError, AttributeError):
                        continue
        except OSError as exc:
            messagebox.showerror('Erro ao abrir log', str(exc), parent=window)

        def selecionar(_event):
            nonlocal selecionando
            selecionando = True
            selecionado = tree.selection()
            campo_nome.config(state='normal' if selecionado else 'disabled')
            nome.set(str(tree.set(selecionado[0], 'nome')) if selecionado else '')
            selecionando = False

        def salvar_nome(*_args):
            if selecionando or not tree.selection():
                return
            item = tree.selection()[0]
            indice, original = registros[item]
            try:
                registros[item][1] = atualizar_nome_contato(indice, original, nome.get())
                tree.set(item, 'nome', nome.get())
            except (OSError, ValueError) as exc:
                messagebox.showerror('Erro ao salvar nome', str(exc), parent=window)
                campo_nome.config(state='disabled')

        tree.bind('<<TreeviewSelect>>', selecionar)
        nome.trace_add('write', salvar_nome)

    def emit(self, kind, value):
        try:
            self.events.put_nowait((kind, value))
        except queue.Full:
            if kind != 'wave':
                self.events.put((kind, value))

    def audio_loop(self, inp, out):
        replay = np.empty(0, dtype=np.float32)
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
                    # Transcreve após a redução, mas antes do filtro de voz e do volume.
                    transcriber = self.transcriber
                    if transcriber:
                        transcriber.submit(samples)
                    if voice:
                        if not was_voice:
                            zi = np.zeros((len(sos), 2))
                        samples, zi = signal.sosfilt(sos, samples, zi=zi)
                    was_voice = voice
                    samples = np.clip(samples * gain, -1, 1).astype(np.float32)
                    with self.replay_lock:
                        self.audio_history.append(samples)
                        if self.pending_replay is not None:
                            replay = self.pending_replay
                            self.pending_replay = None
                    output = samples
                    if replay.size:
                        count = min(len(samples), replay.size)
                        output = samples.copy()
                        output[:count] = replay[:count]
                        replay = replay[count:]
                    underflow = stream.write(output.reshape(-1, 1))
                    self.emit('wave', output[::max(1, len(output)//400)])
                    if overflow or underflow:
                        self.emit('status', 'Áudio ativo; houve falha de tempo. Feche outros programas ou reduza a carga do computador.')
        except Exception as exc:
            self.emit('error', str(exc))
        finally:
            self.emit('stopped', None)

    def capture(self):
        self.capture_event.set()

    def replay(self):
        try:
            seconds = int(self.replay_seconds.get())
        except ValueError:
            seconds = 0
        if not 1 <= seconds <= MAX_REPLAY_SECONDS:
            self.status.set(f'Informe de 1 a {MAX_REPLAY_SECONDS} segundos para o replay.')
            return
        count = seconds * RATE
        blocks = (count + BLOCK - 1) // BLOCK
        with self.replay_lock:
            history = tuple(self.audio_history)
        if not history:
            self.status.set('Aguarde a chegada de áudio para usar o replay.')
            return
        recording = np.concatenate(history[-blocks:])[-count:]
        with self.replay_lock:
            self.pending_replay = recording

    def stop(self):
        self.stop_event.set()
        self.stop_transcription()
        if self.subtitles_enabled.get():
            self.subtitle.set('Áudio parado. Legendas serão retomadas ao iniciar.')
        self.stop_button.config(state='disabled')
        self.replay_button.config(state='disabled')
        self.status.set('Parando áudio...')

    def poll(self):
        self.settings = (self.enabled.get(), self.voice.get(), self.strength.get(), self.gain.get())
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'transcription_event':
                    generation, kind, value = value
                    if generation != self.transcription_generation:
                        continue
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
                elif kind == 'contact_result':
                    self.lookup_button.config(state='normal')
                    self.wrl_button.config(state='normal')
                    contact, warning, fonte = value
                    if contact:
                        self.status.set(f'Contato encontrado em {fonte}.')
                        self.show_contact(contact)
                    else:
                        self.status.set(f'Nenhum contato encontrado em {fonte}.')
                        text = ('Nenhum indicativo exato encontrado entre as primeiras sugestões da busca pública da WRL.'
                                if fonte == 'WRL' else 'Indicativo não encontrado na HamDB. A base pode não incluir esta estação ou prefixos de grupos PX.')
                        messagebox.showinfo('Busca de contato', text)
                    if warning:
                        messagebox.showwarning('Log de buscas', f'Não foi possível salvar a busca no log: {warning}')
                elif kind == 'contact_error':
                    self.lookup_button.config(state='normal')
                    self.wrl_button.config(state='normal')
                    fonte, error = value
                    self.status.set(f'Não foi possível consultar {fonte}.')
                    messagebox.showerror('Busca de contato', error)
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
                    for button in self.language_buttons:
                        button.config(state='normal')
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
                    self.replay_button.config(state='disabled')
                    self.input_box.config(state='readonly')
                    self.output_box.config(state='readonly')
                    if self.status.get() != 'Erro no áudio.':
                        self.status.set('Áudio parado.')
        except queue.Empty:
            pass
        self.root.after(80, self.poll)

    def draw(self, samples):
        self.last_wave = samples.copy()
        self.draw_wave(self.canvas, samples)
        if self.fullscreen_canvas and self.fullscreen_canvas.winfo_exists():
            self.draw_wave(self.fullscreen_canvas, samples)

    @staticmethod
    def draw_wave(canvas, samples):
        width, height = max(canvas.winfo_width(), 2), max(canvas.winfo_height(), 2)
        canvas.delete('all')
        canvas.create_line(0, height / 2, width, height / 2, fill='#34495b')
        points = []
        for i, sample in enumerate(samples):
            points.extend((i * width / max(len(samples) - 1, 1), height / 2 - float(sample) * height * 0.48))
        if len(points) >= 4:
            canvas.create_line(*points, fill='#4de0bb', width=1)

    def open_fullscreen(self):
        if self.fullscreen_window and self.fullscreen_window.winfo_exists():
            self.fullscreen_window.lift()
            return
        window = tk.Toplevel(self.root)
        self.fullscreen_window = window
        window.title('Globo e onda sonora')
        window.configure(background='#050d17')
        window.attributes('-fullscreen', True)
        window.bind('<Escape>', lambda _event: self.close_fullscreen())
        window.protocol('WM_DELETE_WINDOW', self.close_fullscreen)
        frame = ttk.Frame(window, padding=10)
        frame.pack(fill='both', expand=True)
        header = ttk.Frame(frame)
        header.pack(side='top', fill='x')
        prefixo = self.callsign.get().strip().upper()
        try:
            nome = nome_no_historico(prefixo)
        except OSError as exc:
            logging.warning('Não foi possível consultar o histórico: %s', exc)
            nome = None
        titulo = f'{prefixo} - {nome}' if prefixo and nome else prefixo
        self.fullscreen_info = tk.StringVar(value=titulo)
        ttk.Label(header, textvariable=self.fullscreen_info, font=('Consolas', 10, 'bold'),
                  foreground='#a7f5e7').pack(side='left')
        ttk.Button(header, text='SAIR DA TELA CHEIA  (ESC)', command=self.close_fullscreen).pack(side='right')
        wave = ttk.LabelFrame(frame, text='Onda sonora de saída', padding=8)
        wave.pack(side='bottom', fill='x', pady=(8, 0))
        self.fullscreen_canvas = tk.Canvas(wave, background='#101a25', highlightthickness=0, height=160)
        self.fullscreen_canvas.pack(fill='x')
        self.fullscreen_canvas.bind('<Configure>', lambda event: self.draw_wave(event.widget, self.last_wave))
        self.fullscreen_globe = Globo(frame, tela_cheia=True, fonte=self.globo)
        self.fullscreen_globe.pack(fill='both', expand=True)
        match = re.match(r'^([0-9]+)', prefixo)
        if match:
            divisao = match.group(1)
            if any(str(entry.get('divisao')) == divisao for entry in self.fullscreen_globe.divisoes):
                self.fullscreen_globe.search.insert(0, divisao)
                self.fullscreen_globe.find()
                self.fullscreen_info.set(f'{titulo}   |   DIVISÃO {divisao}')
            else:
                self.fullscreen_globe.selected = None
                self.fullscreen_globe.route = None
                self.fullscreen_info.set(f'{titulo}   |   DIVISÃO {divisao} NÃO CADASTRADA')

    def close_fullscreen(self):
        if self.fullscreen_window and self.fullscreen_window.winfo_exists():
            if self.fullscreen_globe:
                self.globo.angle = self.fullscreen_globe.angle
                self.globo.rotating = self.fullscreen_globe.rotating
            self.fullscreen_window.destroy()
        self.fullscreen_window = self.fullscreen_canvas = self.fullscreen_globe = None

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
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
    root = tk.Tk()
    RadioApp(root)
    root.mainloop()
