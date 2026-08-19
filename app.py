from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

@app.route('/')
def home():
    return "API SBS Peru NDF rodando com sucesso!", 200

@app.route('/sbs')
def sbs_promedio():
    raw_data = request.args.get('data', '')
    
    match_data = re.search(r'(\d{2}/\d{2}/\d{4})', raw_data)
    if not match_data:
        return jsonify({'error': 'Data invalida. Use DD/MM/AAAA'}), 400
        
    fecha_str = match_data.group(1)
    partes = fecha_str.split('/')
    fecha_iso = f"{partes[2]}-{partes[1]}-{partes[0]}"
    
    url_sbs = "https://www.sbs.gob.pe/app/pp/SISTIP_PORTAL/Paginas/Publicacion/TipoCambioPromedio.aspx"
    
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,*/*;q=0.8',
        'Accept-Language': 'es-PE,es;q=0.9,en-US;q=0.8,en;q=0.7',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    taxa_sbs = None
    
    # 1. TENTA ACESSAR A SBS (Pode ser bloqueado pelo firewall do governo)
    try:
        res = session.get(url_sbs, headers=headers, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            
            payload = {}
            for input_tag in soup.find_all('input'):
                name = input_tag.get('name')
                if not name:
                    continue
                value = input_tag.get('value', '')
                
                input_type = input_tag.get('type', '').lower()
                if input_type in ['submit', 'button']:
                    if 'Consultar' in value:
                        payload[name] = value
                    continue
                    
                payload[name] = value

            payload['__EVENTTARGET'] = ''
            payload['__EVENTARGUMENT'] = ''

            for key in list(payload.keys()):
                if 'dateInput' in key:
                    payload[key] = fecha_str
                elif 'rdpDate' in key and 'ClientState' not in key:
                    payload[key] = fecha_iso
                elif 'ClientState' in key and 'rdpDate' in key:
                    payload[key] = ''

            if not any('btnConsultar' in k for k in payload):
                payload['ctl00$cphContent$btnConsultar'] = 'Consultar'

            headers['Referer'] = url_sbs
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            
            res2 = session.post(url_sbs, data=payload, headers=headers, timeout=8)
            
            html_limpo = re.sub(r'<[^>]+>', ' ', res2.text)
            html_limpo = re.sub(r'\s+', ' ', html_limpo)
            
            idx = html_limpo.find('Mercado Profesional, Promedio Ponderado')
            if idx != -1:
                bloco = html_limpo[idx:idx+500]
                idx_na = bloco.find('N.A.')
                if idx_na != -1:
                    bloco_final = bloco[idx_na:]
                    match = re.search(r'([0-9]+\.[0-9]{3,6})', bloco_final)
                    if match:
                        taxa_sbs = float(match.group(1))
    except Exception as e:
        print(f"Erro de Conexao com a SBS: {e}")

    # Se achou a taxa na SBS, devolve ela.
    if taxa_sbs is not None:
        return jsonify({
            'fonte': 'SBS_OFICIAL',
            'data': fecha_str, 
            'promedio_ponderado': taxa_sbs
        })
        
    # 2. SE NÃO ACHOU (Contingência Automática BCRP)
    # Entra aqui se a SBS travar, bloquear o IP do Render ou for Feriado
    try:
        url_c = f"https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PD04637PD/json/{fecha_iso}/{fecha_iso}"
        url_v = f"https://estadisticas.bcrp.gob.pe/estadisticas/series/api/PD04638PD/json/{fecha_iso}/{fecha_iso}"
        
        r_c = session.get(url_c, timeout=5).json()
        r_v = session.get(url_v, timeout=5).json()
        
        val_c = float(r_c['periods'][0]['values'][0])
        val_v = float(r_v['periods'][0]['values'][0])
        media = round((val_c + val_v) / 2, 4)
        
        return jsonify({
            'fonte': 'BCRP_CONTINGENCIA',
            'data': fecha_str,
            'promedio_ponderado': media
        })
    except Exception as e:
        return jsonify({'error': 'Falha total. SBS e BCRP indisponíveis.'}), 504

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
