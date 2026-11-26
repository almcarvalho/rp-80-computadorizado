"""Globo ortográfico e consulta das divisões PX."""
import json
import math
import queue
import threading
import unicodedata
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from propagacao import buscar_contornos

BASE = Path(__file__).resolve().parent


def normalizar(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c)).strip()


def contem(ring, lon, lat):
    inside = False
    previous = ring[-1]
    for current in ring:
        x1, y1 = previous[:2]
        x2, y2 = current[:2]
        if (y1 > lat) != (y2 > lat) and lon < (x2-x1) * (lat-y1) / (y2-y1) + x1:
            inside = not inside
        previous = current
    return inside


def rota_esferica(origem, destino):
    def vetor(lon, lat):
        lon, lat = math.radians(lon), math.radians(lat)
        return (math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat))

    a, b = vetor(*origem), vetor(*destino)
    angulo = math.acos(max(-1.0, min(1.0, sum(x*y for x, y in zip(a, b)))))
    if angulo < 1e-8:
        return [origem, destino]
    if abs(math.sin(angulo)) < 1e-8:
        return [origem, destino]
    pontos = []
    for i in range(101):
        t = i / 100
        u = math.sin((1-t)*angulo) / math.sin(angulo)
        v = math.sin(t*angulo) / math.sin(angulo)
        x, y, z = (u*x + v*y for x, y in zip(a, b))
        pontos.append((math.degrees(math.atan2(y, x)), math.degrees(math.atan2(z, math.hypot(x, y)))))
    return pontos


class Globo(ttk.Frame):
    def __init__(self, parent, tela_cheia=False, fonte=None):
        super().__init__(parent, style='Panel.TFrame', padding=12)
        self.angle = -55.0
        self.selected = None
        self.rotating = True
        self.route = None
        self.hit = []
        self.fonte = fonte
        self.drag_start = None
        self.drag_last = None
        self.dragged = False
        self.propagation_enabled = tk.BooleanVar(value=False)
        self.propagation_status = tk.StringVar(value='')
        self.propagation_lines = []
        self.propagation_results = queue.Queue()
        self.propagation_loading = False
        self.propagation_timer = None
        with (BASE / 'paises.geojson').open(encoding='utf-8') as f:
            self.features = json.load(f)['features']
        with (BASE / 'divisoes.json').open(encoding='utf-8-sig') as f:
            self.divisoes = json.load(f)
        with (BASE / 'coordenadas_divisoes.json').open(encoding='utf-8') as f:
            self.coordinates = json.load(f)
        if fonte:
            self.angle, self.rotating, self.route = fonte.angle, fonte.rotating, fonte.route
            if fonte.selected:
                code = fonte.selected['properties'].get('ADM0_A3')
                self.selected = next((feature for feature in self.features if feature['properties'].get('ADM0_A3') == code), None)
        if not tela_cheia:
            ttk.Label(self, text='MAPA DE COMUNICAÇÕES', style='Title.TLabel').pack(anchor='w')
            ttk.Label(self, text='RASTREAMENTO GLOBAL  /  11M', style='Muted.TLabel').pack(anchor='w', pady=(0, 5))
        self.result = tk.StringVar(value='Selecione um país no globo ou pesquise abaixo.')
        if not tela_cheia:
            ttk.Label(self, textvariable=self.result, style='Info.TLabel', wraplength=340,
                      justify='left').pack(fill='x', pady=(4, 8))
        footer = ttk.Frame(self, style='Panel.TFrame')
        if not tela_cheia:
            footer.pack(side='bottom', fill='x')
            ttk.Checkbutton(footer, text='Propagação 11 m (MUF)', variable=self.propagation_enabled,
                            command=self.toggle_propagation).pack(anchor='w')
            ttk.Label(footer, textvariable=self.propagation_status, style='Muted.TLabel',
                      wraplength=340, justify='left').pack(anchor='w')
        self.search = ttk.Entry(footer)
        if not tela_cheia:
            self.search.pack(fill='x', pady=(5, 4))
            self.search.bind('<Return>', lambda e: self.find())
            ttk.Button(footer, text='BUSCAR PAÍS OU DIVISÃO', command=self.find).pack(fill='x')
            ttk.Button(footer, text='RETOMAR ROTAÇÃO', command=self.resume).pack(fill='x', pady=(4, 0))
        self.canvas = tk.Canvas(self, width=360, height=320, bg='#07121e', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<ButtonPress-1>', self.start_drag)
        self.canvas.bind('<B1-Motion>', self.move_drag)
        self.canvas.bind('<ButtonRelease-1>', self.end_drag)
        self.draw()
        self.after(200, self.poll_propagation)

    def toggle_propagation(self):
        if self.propagation_timer:
            self.after_cancel(self.propagation_timer)
            self.propagation_timer = None
        if self.propagation_enabled.get():
            self.update_propagation()
        else:
            self.propagation_status.set('')

    def update_propagation(self):
        self.propagation_timer = None
        if not self.propagation_enabled.get() or self.propagation_loading:
            return
        self.propagation_loading = True
        self.propagation_status.set('Consultando KC2G / GIRO...')
        def worker():
            try:
                self.propagation_results.put((True, buscar_contornos()))
            except Exception as exc:
                self.propagation_results.put((False, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll_propagation(self):
        try:
            while True:
                success, value = self.propagation_results.get_nowait()
                self.propagation_loading = False
                if success:
                    self.propagation_lines, when = value
                    time_text = when.strftime('%d/%m %H:%M %Z') if when else 'horário não informado'
                    self.propagation_status.set(f'MUF 3000 km • {time_text}\nAzul: < 27 MHz • vermelho: ≥ 27 MHz')
                else:
                    self.propagation_status.set('Falha ao atualizar. Dados anteriores podem estar desatualizados.' if self.propagation_lines
                                                else 'Dados de propagação indisponíveis. Verifique a internet.')
                if self.propagation_enabled.get():
                    self.propagation_timer = self.after(15 * 60 * 1000, self.update_propagation)
        except queue.Empty:
            pass
        self.after(200, self.poll_propagation)

    def country_name(self, feature):
        p = feature['properties']
        return p.get('NAME_PT') or p.get('NAME') or p.get('ADMIN')

    def polygons(self, feature):
        geo = feature['geometry']
        if not geo:
            return []
        return [geo['coordinates']] if geo['type'] == 'Polygon' else geo['coordinates'] if geo['type'] == 'MultiPolygon' else []

    def project(self, lon, lat, cx, cy, radius):
        a = math.radians(lon - self.angle)
        b = math.radians(lat)
        return (cx + radius * math.cos(b) * math.sin(a), cy - radius * math.sin(b), math.cos(b) * math.cos(a))

    def draw(self):
        if not self.winfo_exists():
            return
        c = self.canvas
        c.delete('all')
        w, h = max(c.winfo_width(), 360), max(c.winfo_height(), 320)
        cx, cy, radius = w / 2, h / 2, min(w, h) * .41
        c.create_oval(cx-radius-7, cy-radius-7, cx+radius+7, cy+radius+7, outline='#164254', width=1)
        c.create_oval(cx-radius, cy-radius, cx+radius, cy+radius, fill='#0b3045', outline='#2a9fb2', width=2)
        for lat in (-60, -30, 0, 30, 60):
            points = [self.project(lon, lat, cx, cy, radius) for lon in range(-180, 181, 5)]
            visible = [(x, y) for x, y, z in points if z > 0]
            if len(visible) > 1:
                c.create_line(*[v for p in visible for v in p], fill='#155065')
        for feature in self.features:
            for polygon in self.polygons(feature):
                if not polygon:
                    continue
                projected = [self.project(point[0], point[1], cx, cy, radius) for point in polygon[0]]
                visible = [(x, y) for x, y, z in projected if z > 0]
                if len(visible) >= 3:
                    color = '#56e0c2' if feature is self.selected else '#257a81'
                    c.create_polygon(*[v for p in visible for v in p], fill=color, outline='#48acaa', width=1)
        propagation_on = self.fonte.propagation_enabled.get() if self.fonte else self.propagation_enabled.get()
        propagation_lines = self.fonte.propagation_lines if self.fonte else self.propagation_lines
        if propagation_on:
            for level, points in propagation_lines:
                color = '#ff534d' if level >= 27 else '#48b6ff'
                previous = None
                for point in points:
                    try:
                        projected = self.project(float(point[0]), float(point[1]), cx, cy, radius)
                    except (ValueError, TypeError, IndexError):
                        previous = None
                        continue
                    if previous and previous[2] > 0 and projected[2] > 0:
                        c.create_line(previous[0], previous[1], projected[0], projected[1], fill=color, width=2)
                    previous = projected
        if self.route:
            projected = [self.project(lon, lat, cx, cy, radius) for lon, lat in self.route]
            for first, second in zip(projected, projected[1:]):
                if first[2] >= 0 and second[2] >= 0:
                    c.create_line(first[0], first[1], second[0], second[1], fill='#ffbf63', width=3)
            for x, y, visible in (projected[0], projected[-1]):
                if visible >= 0:
                    c.create_oval(x-4, y-4, x+4, y+4, fill='#fff3c3', outline='#ff9d42', width=2)
        state = '● LIVE' if self.rotating else '◆ ROTA FIXADA'
        c.create_text(12, 12, text=f'{state}   /   ORBITAL VIEW', anchor='nw', fill='#56e0c2', font=('Consolas', 9, 'bold'))
        if self.fonte and self.selected:
            c.create_text(12, 32, text=self.country_name(self.selected).upper(), anchor='nw',
                          fill='#e8fff9', font=('Consolas', 12, 'bold'))
        if self.rotating:
            self.angle = (self.angle + .35 + 180) % 360 - 180
        self.after(100, self.draw)

    def resume(self):
        self.route = None
        self.rotating = True

    def start_drag(self, event):
        self.drag_start = (event.x, event.y)
        self.drag_last = event.x
        self.dragged = False

    def move_drag(self, event):
        if self.drag_start is None:
            return
        if abs(event.x - self.drag_start[0]) > 3 or abs(event.y - self.drag_start[1]) > 3:
            self.dragged = True
        if self.dragged:
            width = max(self.canvas.winfo_width(), 1)
            self.angle = (self.angle - (event.x - self.drag_last) * 180 / width + 180) % 360 - 180
            self.rotating = False
        self.drag_last = event.x

    def end_drag(self, event):
        if self.drag_start is not None and not self.dragged:
            self.click(event)
        self.drag_start = self.drag_last = None

    def click(self, event):
        w, h = max(self.canvas.winfo_width(), 360), max(self.canvas.winfo_height(), 320)
        radius = min(w, h) * .41
        x, y = (event.x-w/2)/radius, -(event.y-h/2)/radius
        if x*x+y*y >= 1:
            return
        lat = math.degrees(math.asin(y))
        lon = ((self.angle + math.degrees(math.atan2(x, math.sqrt(max(0, 1-x*x-y*y)))) + 180) % 360) - 180
        for feature in self.features:
            for polygon in self.polygons(feature):
                if polygon and contem(polygon[0], lon, lat) and not any(contem(hole, lon, lat) for hole in polygon[1:]):
                    self.select(feature)
                    return
        self.result.set('Oceano ou território pequeno. Busque pelo nome do país.')

    def select(self, feature):
        self.selected = feature
        p = feature['properties']
        code = p.get('ADM0_A3')
        matches = [d for d in self.divisoes if d.get('iso') == code]
        divisions = ', '.join(str(d['divisao']) for d in matches) or 'não cadastrada'
        self.result.set(f"{self.country_name(feature).upper()}\nDIVISÃO  /  {divisions}")

    def find(self):
        query = normalizar(self.search.get())
        if not query:
            self.result.set('Digite um país ou número de divisão.')
            return
        entries = [d for d in self.divisoes if normalizar(str(d['divisao'])) == query
                   or normalizar(d['pais']) == query or normalizar(d.get('nome_pdf', '')) == query]
        if entries:
            entry = entries[0]
            self.rotating = False
            self.route = None
            feature = next((f for f in self.features if entry.get('iso') and
                            f['properties'].get('ADM0_A3') == entry['iso']), None)
            self.selected = feature
            status = '  /  EXCLUÍDA NO PDF' if entry.get('situacao') == 'excluída' else ''
            coords = self.coordinates.get(str(entry['divisao']))
            if coords and entry.get('situacao') != 'excluída':
                origem = (-55.0, -10.0)
                destino = (coords['lon'], coords['lat'])
                self.route = rota_esferica(origem, destino)
                delta = (destino[0] - origem[0] + 180) % 360 - 180
                self.angle = (origem[0] + delta / 2 + 180) % 360 - 180
                route_text = '\nROTA  /  BRASIL → DESTINO (APROXIMADA)'
            else:
                route_text = '\nSEM COORDENADAS DISPONÍVEIS PARA A ROTA'
            self.result.set(f"PAÍS / TERRITÓRIO  /  {entry['pais'].upper()}\nDIVISÃO  /  {entry['divisao']}{status}{route_text}")
            return
        for feature in self.features:
            p = feature['properties']
            names = [self.country_name(feature), p.get('NAME_EN') or '', p.get('ADMIN') or '', p.get('ISO_A3') or '']
            if any(normalizar(n) == query for n in names):
                self.select(feature)
                self.angle = float(p.get('LABEL_X') or 0)
                return
        self.result.set('País ou divisão não encontrado. Tente o nome completo.')
