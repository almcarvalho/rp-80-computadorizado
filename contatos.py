"""Consultas de indicativos em fontes independentes."""
import json
import logging
import os
import re
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

LOG_CONTATOS = Path(__file__).resolve().parent / 'buscas_contatos.jsonl'
logger = logging.getLogger(__name__)
BASE = Path(__file__).resolve().parent
WRL_APP = 'https://app.worldradioleague.com'
WRL_PUBLIC_API = 'https://ebuveblscfmqpztairyk.supabase.co'
_wrl_public_key = None
_log_lock = threading.RLock()


def ocultar_segredos(value):
    if isinstance(value, dict):
        return {key: '[OCULTO]' if any(word in key.lower() for word in ('key', 'token', 'password', 'secret', 'authorization'))
                else ocultar_segredos(item) for key, item in value.items()}
    if isinstance(value, list):
        return [ocultar_segredos(item) for item in value]
    return value


def buscar_contato(prefixo):
    prefixo = prefixo.strip().upper()
    if not re.fullmatch(r'[A-Z0-9/]{2,24}', prefixo):
        raise ValueError('Digite o indicativo completo usando letras, números e, se necessário, /.')
    url = f'https://api.hamdb.org/v1/{quote(prefixo, safe="")}/json/pxcontrol'
    req = Request(url, headers={'User-Agent': 'PX-Control/1.0', 'Accept': 'application/json'})
    logger.info('API HamDB: GET %s', url)
    try:
        with urlopen(req, timeout=12) as response:
            payload = json.load(response)
            logger.info('API HamDB: HTTP %s; resposta: %s', response.status,
                        json.dumps(ocultar_segredos(payload), ensure_ascii=False))
    except HTTPError as exc:
        logger.error('API HamDB: erro HTTP %s (%s)', exc.code, exc.reason)
        raise
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        logger.error('API HamDB: falha na consulta ou leitura da resposta: %s', exc)
        raise
    hamdb = payload.get('hamdb', {})
    status = hamdb.get('messages', {}).get('status')
    if status == 'NOT_FOUND':
        return None
    if status != 'OK' or not isinstance(hamdb.get('callsign'), dict):
        raise ValueError('A HamDB retornou uma resposta inesperada.')
    data = hamdb['callsign']
    nome = ' '.join(str(data.get(k) or '').strip() for k in ('fname', 'mi', 'name', 'suffix')).strip()
    nome = ' '.join(nome.split())
    regiao = ', '.join(str(data.get(k) or '').strip() for k in ('addr2', 'state') if str(data.get(k) or '').strip())
    return {
        'prefixo': str(data.get('call') or prefixo), 'nome': nome or 'Não informado',
        'horario': datetime.now().isoformat(timespec='seconds'),
        'regiao': regiao or 'Não informada', 'pais': data.get('country') or 'Não informado',
        'grid': data.get('grid') or 'Não informado', 'classe': data.get('class') or 'Não informada',
        'validade': data.get('expires') or 'Não informada', 'fonte': 'HamDB',
    }


def chave_wrl():
    chave = os.environ.get('WRL_API_KEY', '').strip()
    if chave:
        return chave
    path = BASE / '.env'
    if path.is_file():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            name, sep, value = line.partition('=')
            if sep and name.strip() == 'WRL_API_KEY':
                return value.strip().strip('"\'')
    raise ValueError('Configure WRL_API_KEY no arquivo .env.')


def buscar_wrl(prefixo):
    prefixo = prefixo.strip().upper()
    if not re.fullmatch(r'[A-Z0-9/]{2,24}', prefixo):
        raise ValueError('Digite o indicativo completo usando letras, números e, se necessário, /.')
    chave = chave_wrl()
    if not chave:
        raise ValueError('Configure WRL_API_KEY no arquivo .env.')
    url = 'https://api.worldradioleague.com/v1/contacts?' + urlencode({'call': prefixo, 'limit': 1})
    req = Request(url, headers={'Authorization': 'Bearer ' + chave, 'Accept': 'application/json', 'User-Agent': 'PX-Control/1.0'})
    logger.info('API WRL: GET %s (autorização oculta)', url)
    try:
        with urlopen(req, timeout=12) as response:
            payload = json.load(response)
            logger.info('API WRL: HTTP %s; resposta: %s', response.status,
                        json.dumps(ocultar_segredos(payload), ensure_ascii=False))
    except HTTPError as exc:
        logger.error('API WRL: erro HTTP %s', exc.code)
        raise ValueError(f'Consulta WRL falhou (HTTP {exc.code}). Verifique a chave, permissões e conexão.') from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        logger.error('API WRL: falha de conexão ou resposta inválida: %s', type(exc).__name__)
        raise ValueError('Não foi possível conectar à API WRL ou interpretar sua resposta.') from exc
    if not isinstance(payload, dict) or payload.get('error') is not None or not isinstance(payload.get('data'), list):
        raise ValueError('A API WRL retornou uma resposta inesperada.')
    if not payload['data']:
        return None
    data = payload['data'][0]
    if not isinstance(data, dict):
        raise ValueError('A API WRL retornou um contato inválido.')
    regiao = ', '.join(str(data[k]) for k in ('qth', 'state') if data.get(k))
    return {'prefixo': data.get('call') or prefixo, 'nome': data.get('name') or 'Não informado',
            'horario': datetime.now().isoformat(timespec='seconds'), 'regiao': regiao or 'Não informada',
            'pais': 'Não informado pela API', 'grid': data.get('gridsquare') or 'Não informado',
            'classe': 'Não informada', 'validade': 'Não informada', 'fonte': 'WRL (seus contatos)',
            'horario_contato': data.get('timestamp') or 'Não informado', 'banda': data.get('band'), 'modo': data.get('mode')}


def buscar_wrl_publico(prefixo):
    """Usa a consulta pública utilizada pelo site; não envia a chave pessoal da WRL."""
    global _wrl_public_key
    prefixo = prefixo.strip().upper()
    if not re.fullmatch(r'[A-Z0-9/]{2,24}', prefixo):
        raise ValueError('Digite o indicativo completo usando letras, números e, se necessário, /.')
    try:
        if not _wrl_public_key:
            with urlopen(Request(WRL_APP + '/', headers={'User-Agent': 'PX-Control/1.0'}), timeout=15) as response:
                html = response.read(256_000).decode('utf-8')
            match = re.search(r'src="(/static/js/main\.[a-zA-Z0-9]+\.js)"', html)
            if not match:
                raise ValueError('Não foi possível localizar a configuração pública da WRL.')
            with urlopen(Request(WRL_APP + match.group(1), headers={'User-Agent': 'PX-Control/1.0'}), timeout=25) as response:
                script = response.read(12_000_000).decode('utf-8')
            key_match = re.search(r'REACT_APP_SUPABASE_ANON_KEY:"([A-Za-z0-9_.-]+)"', script)
            url_match = re.search(r'REACT_APP_SUPABASE_URL:"(https://[^"]+)"', script)
            if not key_match or not url_match or url_match.group(1) != WRL_PUBLIC_API:
                raise ValueError('A configuração pública da WRL mudou; consulte o site da WRL.')
            _wrl_public_key = key_match.group(1)
        url = WRL_PUBLIC_API + '/rest/v1/rpc/search_callsign'
        data = json.dumps({'p_search_value': prefixo.lower(), 'p_limit': 5}).encode('utf-8')
        req = Request(url, data=data, method='POST', headers={
            'apikey': _wrl_public_key, 'Authorization': 'Bearer ' + _wrl_public_key,
            'Content-Type': 'application/json', 'Accept': 'application/json', 'Origin': WRL_APP,
            'User-Agent': 'PX-Control/1.0'})
        logger.info('API pública WRL: POST %s; indicativo=%s (credencial pública oculta)', url, prefixo)
        with urlopen(req, timeout=15) as response:
            results = json.load(response)
            logger.info('API pública WRL: HTTP %s; resposta: %s', response.status,
                        json.dumps(ocultar_segredos(results), ensure_ascii=False))
    except HTTPError as exc:
        logger.error('Consulta pública WRL: HTTP %s', exc.code)
        raise ValueError(f'Consulta pública WRL falhou (HTTP {exc.code}).') from exc
    except (URLError, TimeoutError, OSError, UnicodeError) as exc:
        logger.error('Consulta pública WRL: erro de conexão: %s', type(exc).__name__)
        raise ValueError('Não foi possível acessar a busca pública da WRL.') from exc
    if not isinstance(results, list):
        raise ValueError('A busca pública da WRL retornou uma resposta inesperada.')
    data = next((item for item in results if isinstance(item, dict) and str(item.get('callsign', '')).strip().upper() == prefixo), None)
    if data is None:
        return None
    nome = data.get('fullName') or ' '.join(str(data.get(k) or '').strip() for k in ('firstName', 'lastName')).strip()
    regiao = ', '.join(str(data.get(k) or '').strip() for k in ('city', 'state') if data.get(k))
    return {'prefixo': data['callsign'], 'nome': nome or 'Não informado',
            'horario': datetime.now().isoformat(timespec='seconds'), 'regiao': regiao or 'Não informada',
            'pais': data.get('country') or 'Não informado', 'grid': data.get('grid') or 'Não informado',
            'classe': 'Não informada', 'validade': 'Não informada', 'fonte': 'WRL (busca pública)'}


def salvar_contato(contato):
    with _log_lock:
        with LOG_CONTATOS.open('a', encoding='utf-8') as arquivo:
            arquivo.write(json.dumps(contato, ensure_ascii=False) + '\n')


def atualizar_nome_contato(indice, linha_original, nome):
    """Atualiza uma linha sem perder novas buscas adicionadas depois da abertura do log."""
    with _log_lock:
        linhas = LOG_CONTATOS.read_text(encoding='utf-8').splitlines(keepends=True)
        if indice >= len(linhas) or linhas[indice].rstrip('\r\n') != linha_original:
            raise ValueError('O histórico mudou. Feche e abra o log novamente antes de editar.')
        registro = json.loads(linha_original)
        registro['nome'] = nome
        nova_linha = json.dumps(registro, ensure_ascii=False)
        linhas[indice] = nova_linha + '\n'
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=LOG_CONTATOS.parent,
                                             prefix='.buscas_', suffix='.tmp', delete=False, newline='') as arquivo:
                temp_path = Path(arquivo.name)
                arquivo.writelines(linhas)
            os.replace(temp_path, LOG_CONTATOS)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()
        return nova_linha


def registrar_busca(prefixo, contato, fonte='HamDB'):
    registro = contato if contato is not None else {
        'prefixo': prefixo.strip().upper(),
        'nome': 'Não encontrado',
        'horario': datetime.now().isoformat(timespec='seconds'),
        'regiao': '—', 'pais': '—', 'fonte': fonte,
    }
    salvar_contato(registro)


def nome_no_historico(prefixo):
    """Retorna o nome conhecido mais recente com correspondência exata."""
    prefixo = prefixo.strip().upper()
    if not prefixo:
        return None
    with _log_lock:
        if not LOG_CONTATOS.exists():
            return None
        linhas = LOG_CONTATOS.read_text(encoding='utf-8').splitlines()
    for linha in reversed(linhas):
        try:
            entry = json.loads(linha)
            if not isinstance(entry, dict) or str(entry.get('prefixo') or '').strip().upper() != prefixo:
                continue
            nome = str(entry.get('nome') or '').strip()
            if nome and nome.casefold() not in {'não encontrado', 'nao encontrado', 'não informado', 'nao informado', '—', '-'}:
                return nome
        except (ValueError, TypeError):
            continue
    return None
