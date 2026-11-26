"""Globo ortográfico e consulta das divisões PX."""
import json
import math
import unicodedata
from pathlib import Path
import tkinter as tk
from tkinter import ttk

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
    def __init__(self, parent):
        super().__init__(parent, style='Panel.TFrame', padding=12)
        self.angle = -55.0
        self.selected = None
        self.rotating = True
        self.route = None
        self.hit = []
        with (BASE / 'paises.geojson').open(encoding='utf-8') as f:
            self.features = json.load(f)['features']
        with (BASE / 'divisoes.json').open(encoding='utf-8-sig') as f:
            self.divisoes = json.load(f)
        with (BASE / 'coordenadas_divisoes.json').open(encoding='utf-8') as f:
            self.coordinates = json.load(f)
        ttk.Label(self, text='MAPA DE COMUNICAÇÕES', style='Title.TLabel').pack(anchor='w')
        ttk.Label(self, text='RASTREAMENTO GLOBAL  /  11M', style='Muted.TLabel').pack(anchor='w', pady=(0, 5))
        self.canvas = tk.Canvas(self, width=360, height=320, bg='#07121e', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Button-1>', self.click)
        self.search = ttk.Entry(self)
        self.search.pack(fill='x', pady=(5, 4))
        self.search.bind('<Return>', lambda e: self.find())
        ttk.Button(self, text='BUSCAR PAÍS OU DIVISÃO', command=self.find).pack(fill='x')
        ttk.Button(self, text='RETOMAR ROTAÇÃO', command=self.resume).pack(fill='x', pady=(4, 0))
        self.result = tk.StringVar(value='Selecione um país no globo ou pesquise acima.')
        ttk.Label(self, textvariable=self.result, style='Info.TLabel', wraplength=340, justify='left').pack(fill='x', pady=(9, 5))
        self.draw()

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
        if self.rotating:
            self.angle = (self.angle + .35 + 180) % 360 - 180
        self.after(100, self.draw)

    def resume(self):
        self.route = None
        self.rotating = True

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
            self.result.set(f"{entry['pais'].upper()}\nDIVISÃO  /  {entry['divisao']}{status}{route_text}")
            return
        for feature in self.features:
            p = feature['properties']
            names = [self.country_name(feature), p.get('NAME_EN') or '', p.get('ADMIN') or '', p.get('ISO_A3') or '']
            if any(normalizar(n) == query for n in names):
                self.select(feature)
                self.angle = float(p.get('LABEL_X') or 0)
                return
        self.result.set('País ou divisão não encontrado. Tente o nome completo.')
