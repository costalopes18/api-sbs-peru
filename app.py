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
        
    fecha_str = match_data.group(1) # Ex: 14/08/2026
    partes = fecha_str.split('/')
    dia, mes, ano = partes[0], partes[1], partes[2]
    fecha_iso = f"{ano}-{mes}-{dia}"
    
    url_sbs = "https://www.sbs.gob.pe/app/pp/SISTIP_PORTAL/Paginas/Publicacion/TipoCambioPromedio.aspx"
    
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }
    
    taxa_sbs = None
    
    try:
        # 1. Acesso inicial para extrair ViewState e Cookies
        res = session.get(url_sbs, headers=headers, timeout=10)
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
                    if 'btnConsultar' in name or 'Consultar' in value:
                        payload[name] = value
                    continue
                payload[name] = value

            payload['__EVENTTARGET'] = ''
            payload['__EVENTARGUMENT'] = ''

            # Preenche os campos do calendário Telerik exigidos pelo ASP.NET
            for key in list(payload.keys()):
                if 'dateInput' in key and 'ClientState' not in key:
                    payload[key] = fecha_str
                elif 'rdpDate' in key and 'ClientState' not in key:
                    payload[key] = fecha_iso
                elif 'ClientState' in key:
                    # Injeção do objeto de estado que valida a data no servidor SBS
                    payload[key] = f'{{"enabled":true,"emptyMessage":"","validationText":"{fecha_iso}-00-00-00","valueAsString":"{fecha_iso}-00-00-00","minDateStr":"1000-01-01-00-00-00","maxDateStr":"9999-12-31-00-00-00"}}'

            if not any('btnConsultar' in k for k in payload):
                payload['ctl00$cphContent$btnConsultar'] = 'Consultar'

            post_headers = headers.copy()
            post_headers['Referer'] = url_sbs
            post_headers['Origin'] = 'https://www.sbs.gob.pe'
            post_headers['Content-Type'] = 'application/x-www-form-urlencoded'
            
            res2 = session.post(url_sbs, data=payload, headers=post_headers, timeout=10)
            
            soup2 = BeautifulSoup(res2.text, 'html.parser')
            texto_completo = soup2.get_text(separator=' ', strip=True)
            
            # Localiza a tabela Mercado Profesional no HTML processado
            idx = texto_completo.find("Mercado Profesional")
            if idx != -1:
                trecho = texto_completo[idx:idx+300]
                numeros = re.findall(r'\b\d{1,2}\.\d{4}\b', trecho)
                if numeros:
                    taxa_sbs = float(numeros[0])
    except Exception as e:
        print(f"Erro ao consultar SBS: {e}")

    # Retorna o valor cravado extraído da SBS (ex: 3.3646)
    if taxa_sbs is not None:
        return jsonify({
            'fonte': 'SBS_OFICIAL',
            'data': fecha_str, 
            'promedio_ponderado': taxa_sbs
        })
        
    # Contingência BCRP
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
    except Exception:
        return jsonify({'error': 'Falha total SBS e BCRP'}), 504

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
