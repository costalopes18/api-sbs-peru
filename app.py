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
    
    # Extrai estritamente o padrao DD/MM/AAAA
    match_data = re.search(r'(\d{2}/\d{2}/\d{4})', raw_data)
    if not match_data:
        return jsonify({'error': 'Data invalida. Use DD/MM/AAAA'}), 400
        
    fecha_str = match_data.group(1) # Ex: 10/08/2026
    
    try:
        url = "https://www.sbs.gob.pe/app/pp/SISTIP_PORTAL/Paginas/Publicacion/TipoCambioPromedio.aspx"
        
        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,*/*;q=0.8',
            'Connection': 'keep-alive'
        }
        
        # 1. Acesso espião (Copia a tela toda)
        res = session.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # CLONADOR: Pega ABSOLUTAMENTE TODOS os campos invisíveis do site
        payload = {}
        for input_tag in soup.find_all('input'):
            name = input_tag.get('name')
            if not name:
                continue
            value = input_tag.get('value', '')
            
            # Filtra os botoes para nao clicar em "Exportar Excel" sem querer
            input_type = input_tag.get('type', '').lower()
            if input_type in ['submit', 'button']:
                if 'Consultar' in value:
                    payload[name] = value
                continue
                
            payload[name] = value

        # Zera eventos para garantir que o botao de Consultar assuma
        payload['__EVENTTARGET'] = ''
        payload['__EVENTARGUMENT'] = ''

        partes = fecha_str.split('/')
        fecha_iso = f"{partes[2]}-{partes[1]}-{partes[0]}"
        
        # 2. Injeta as datas dinamicamente e anula o estado do calendario
        for key in list(payload.keys()):
            if 'dateInput' in key:
                payload[key] = fecha_str
            elif 'rdpDate' in key and 'ClientState' not in key:
                payload[key] = fecha_iso
            elif 'ClientState' in key and 'rdpDate' in key:
                payload[key] = '' # Limpar isso impede que o calendario force a data de hoje

        if not any('btnConsultar' in k for k in payload):
            payload['ctl00$cphContent$btnConsultar'] = 'Consultar'

        headers['Referer'] = url
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
        
        # 3. Envia o pacote completo igual a um humano
        res2 = session.post(url, data=payload, headers=headers, timeout=15)
        
        # 4. Captura a taxa
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
                    return jsonify({
                        'data': fecha_str, 
                        'promedio_ponderado': float(match.group(1))
                    })
                    
        return jsonify({'error': 'Taxa nao encontrada. SBS pode ter bloqueado ou nao ha operacao nesta data.'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
    
