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
    fecha_str = request.args.get('data') # Exemplo: 10/08/2026
    if not fecha_str:
        return jsonify({'error': 'Data nao fornecida'}), 400
        
    try:
        url = "https://www.sbs.gob.pe/app/pp/SISTIP_PORTAL/Paginas/Publicacion/TipoCambioPromedio.aspx"
        
        session = requests.Session()
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        
        # 1. Acesso espião
        res = session.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        viewstate = soup.find('input', id='__VIEWSTATE')['value']
        viewstategenerator = soup.find('input', id='__VIEWSTATEGENERATOR')['value']
        eventvalidation = soup.find('input', id='__EVENTVALIDATION')['value']
        
        # Formato iso
        fecha_iso = f"{fecha_str[6:10]}-{fecha_str[3:5]}-{fecha_str[0:2]}"
        
        # 2. Maleta de Dados
        data = {
            '__VIEWSTATE': viewstate,
            '__VIEWSTATEGENERATOR': viewstategenerator,
            '__EVENTVALIDATION': eventvalidation,
            'ctl00$cphContent$rdpDate': fecha_iso,
            'ctl00$cphContent$rdpDate$dateInput': fecha_str,
            'ctl00$cphContent$btnConsultar': 'Consultar'
        }
        
        # 3. POST simulando humano
        res2 = session.post(url, data=data, headers=headers, timeout=10)
        
        html_limpo = re.sub(r'<[^>]+>', ' ', res2.text)
        html_limpo = re.sub(r'\s+', ' ', html_limpo)
        
        idx = html_limpo.find('Mercado Profesional, Promedio Ponderado')
        if idx != -1:
            bloco = html_limpo[idx:]
            idx_na = bloco.find('N.A.')
            if idx_na != -1:
                bloco_final = bloco[idx_na:]
                match = re.search(r'([0-9]+\.[0-9]{3,6})', bloco_final)
                if match:
                    return jsonify({
                        'data': fecha_str, 
                        'promedio_ponderado': float(match.group(1))
                    })
                    
        return jsonify({'error': 'Taxa nao encontrada no HTML'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
