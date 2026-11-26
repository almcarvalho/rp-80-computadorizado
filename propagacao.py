"""Contornos públicos de MUF(3000 km), em MHz, fornecidos por KC2G/GIRO."""
import json
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen

URL = 'https://prop.kc2g.com/renders/current/mufd-normal-now.geojson'


def buscar_contornos():
    request = Request(URL, headers={'User-Agent': 'PX-Control/1.0', 'Accept': 'application/geo+json, application/json'})
    with urlopen(request, timeout=20) as response:
        stamp = response.headers.get('Last-Modified')
        payload = json.load(response)
    if not isinstance(payload, dict) or not isinstance(payload.get('features'), list):
        raise ValueError('Formato dos dados de propagação não reconhecido.')
    lines = []
    for feature in payload['features']:
        geometry = feature.get('geometry') or {}
        properties = feature.get('properties') or {}
        if geometry.get('type') != 'LineString':
            continue
        points = geometry.get('coordinates')
        level = properties.get('level-value')
        if isinstance(level, (float, int)) and isinstance(points, list) and len(points) > 1:
            simplified = points[::3]
            if simplified[-1] != points[-1]:
                simplified.append(points[-1])
            lines.append((float(level), simplified))
    if not lines:
        raise ValueError('A fonte não retornou contornos de MUF válidos.')
    try:
        when = parsedate_to_datetime(stamp).astimezone() if stamp else None
    except (TypeError, ValueError, OverflowError):
        when = None
    return lines, when
