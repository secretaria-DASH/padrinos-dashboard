import json
import os
import re
import requests
from flask import Flask, render_template, request, jsonify, send_from_directory, Response
import pdfplumber

app = Flask(__name__, static_folder='static', template_folder='.')

DATA_FILE   = os.path.join(os.path.dirname(__file__), 'data', 'campaigns.json')
CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'data', 'config.json')
UPLOAD_DIR  = os.path.join(os.path.dirname(__file__), 'uploads')
BREVO_BASE  = 'https://api.brevo.com/v3'


# ── helpers ──────────────────────────────────────────────────────────────────

def load_data():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_config():
    # Env var takes priority (used in production / Render)
    env_key = os.environ.get('BREVO_API_KEY', '')
    if env_key:
        return {'brevo_api_key': env_key}
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {'brevo_api_key': ''}

def save_config(cfg):
    # Only save to file when running locally (env var not set)
    if not os.environ.get('BREVO_API_KEY'):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)

def brevo_headers():
    return {'api-key': load_config().get('brevo_api_key', ''), 'Accept': 'application/json'}

def brevo_get(endpoint):
    r = requests.get(f'{BREVO_BASE}/{endpoint}', headers=brevo_headers(), timeout=15)
    r.raise_for_status()
    return r.json()


# ── PDF parser ────────────────────────────────────────────────────────────────

def parse_number(text):
    if text is None:
        return 0
    m = re.search(r'[\d.,]+', str(text).strip())
    if not m:
        return 0
    try:
        return float(m.group().replace(',', '.'))
    except ValueError:
        return 0

def parse_pdf(filepath):
    data = {}
    full_text = ''
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            full_text += (page.extract_text() or '') + '\n'

    for line in full_text.splitlines():
        m = re.search(r'Padrinos\s*[-–]\s*(\w+)', line, re.IGNORECASE)
        if m:
            data['nombre'] = m.group(1).capitalize()
            break

    year = '2026'
    for line in full_text.splitlines():
        m = re.search(r'\b(202\d)\b', line)
        if m:
            year = m.group(1)
            break

    data['mes'] = f"{data.get('nombre', 'Campaña')} {year}"
    data['id']  = f"{data.get('nombre', 'campana').lower()}-{year}"

    for i, line in enumerate(full_text.splitlines()):
        if 'Asunto' in line and i + 1 < len(full_text.splitlines()):
            data['asunto'] = full_text.splitlines()[i + 1].strip()
            break

    m = re.search(r'Enviada el\s+(\w+\s+\d+,\s+\d{4})', full_text)
    data['fecha_envio'] = m.group(1) if m else ''

    def rex(pattern):
        m = re.search(pattern, full_text)
        return parse_number(m.group(1)) if m else 0

    data['enviadas']           = int(rex(r'Enviadas\s*\n([\d]+)'))
    data['entregadas']         = int(rex(r'Entregados\s*\n([\d]+)'))
    data['indice_entrega']     = rex(r'Índice de entrega\s*\n([\d.,]+)%')
    data['soft_bounces']       = int(rex(r'Soft bounces\s*\n([\d]+)'))
    data['soft_bounces_pct']   = rex(r'Soft bounces\s*\n[\d]+\s*\(([\d.,]+)%\)')
    data['hard_bounces']       = int(rex(r'Hard bounces\s*\n([\d]+)'))
    data['hard_bounces_pct']   = 0
    data['aperturas_unicas']   = int(rex(r'Aperturas\s*\n([\d]+)\s*\nTasa'))
    data['tasa_apertura']      = rex(r'Tasa de apertura\s*\n([\d.,]+)%')
    data['total_aperturas']    = int(rex(r'Total de aperturas\s*\n([\d]+)'))
    data['aperturas_apple_mpp']= int(rex(r'Aperturas de Apple MPP\s*\n([\d]+)'))
    data['clics_unicos']       = int(rex(r'Clics\s*\n([\d]+)\s*\nClick-through'))
    data['ctr']                = rex(r'Click-through rate\s*\n([\d.,]+)%')
    data['total_clics']        = int(rex(r'Total de clics\s*\n([\d]+)'))
    data['click_to_open_rate'] = rex(r'Click-to-open rate\s*\n([\d.,]+)%')
    data['cancelaciones_pct']  = rex(r'Tasa de cancelaciones de suscripción\s*\n([\d.,]+)%')
    data['spam']               = int(rex(r'Quejas de spam\s*\n([\d]+)'))

    listas = []
    for m in re.finditer(r'([A-Z][A-Z\s]+)\s+([\d]+) contacts', full_text):
        listas.append({'nombre': m.group(1).strip(), 'contactos': int(m.group(2))})
    data['listas'] = listas

    return data


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/campaigns')
def get_campaigns():
    return jsonify(load_data())

# Settings
@app.route('/api/settings', methods=['GET'])
def get_settings():
    cfg = load_config()
    key = cfg.get('brevo_api_key', '')
    return jsonify({'has_key': bool(key), 'key_preview': f"...{key[-6:]}" if len(key) > 6 else ''})

@app.route('/api/settings', methods=['POST'])
def save_settings():
    body = request.get_json()
    cfg = load_config()
    cfg['brevo_api_key'] = body.get('brevo_api_key', '').strip()
    save_config(cfg)
    return jsonify({'success': True})

# Brevo: test connection
@app.route('/api/brevo/test')
def brevo_test():
    try:
        data = brevo_get('account')
        return jsonify({'ok': True, 'email': data.get('email'), 'company': data.get('companyName')})
    except requests.HTTPError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# Brevo: get email HTML preview (proxied so iframe works)
@app.route('/api/brevo/preview/<int:brevo_id>')
def brevo_preview(brevo_id):
    try:
        data = brevo_get(f'emailCampaigns/{brevo_id}')
        html = data.get('htmlContent', '<p>Sin contenido HTML disponible</p>')
        # Inject a small base tag and sandbox styles so it renders well in iframe
        inject = """<base target="_blank">
<style>
  body { font-family: Arial, sans-serif !important; }
  * { max-width: 100% !important; box-sizing: border-box; }
</style>"""
        html = html.replace('</head>', inject + '</head>', 1) if '</head>' in html else inject + html
        return Response(html, content_type='text/html; charset=utf-8')
    except requests.HTTPError as e:
        return Response(f'<p style="color:red;font-family:sans-serif;padding:24px">Error al cargar el email: {e}</p>', content_type='text/html')
    except Exception as e:
        return Response(f'<p style="color:red;font-family:sans-serif;padding:24px">Error: {e}</p>', content_type='text/html')

# Brevo: fetch campaign detail (stats + subject)
@app.route('/api/brevo/campaign/<int:brevo_id>')
def brevo_campaign(brevo_id):
    try:
        return jsonify(brevo_get(f'emailCampaigns/{brevo_id}'))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Brevo: sync all campaigns stats from API
@app.route('/api/brevo/sync', methods=['POST'])
def brevo_sync():
    campaigns = load_data()
    updated = []
    errors  = []
    for c in campaigns:
        bid = c.get('brevo_id')
        if not bid:
            continue
        try:
            remote = brevo_get(f'emailCampaigns/{bid}')
            stats  = remote.get('statistics', {}).get('globalStats', {})
            sent   = stats.get('sent', c['enviadas'])
            deliv  = stats.get('delivered', c['entregadas'])
            c['enviadas']            = sent
            c['entregadas']          = deliv
            c['indice_entrega']      = round(deliv / sent * 100, 2) if sent else c['indice_entrega']
            c['soft_bounces']        = stats.get('softBounces', c['soft_bounces'])
            c['soft_bounces_pct']    = round(c['soft_bounces'] / sent * 100, 2) if sent else c['soft_bounces_pct']
            c['hard_bounces']        = stats.get('hardBounces', c['hard_bounces'])
            c['aperturas_unicas']    = stats.get('uniqueViews', c['aperturas_unicas'])
            c['total_aperturas']     = stats.get('viewed', c['total_aperturas'])
            c['tasa_apertura']       = round(c['aperturas_unicas'] / deliv * 100, 2) if deliv else c['tasa_apertura']
            c['clics_unicos']        = stats.get('uniqueClicks', c['clics_unicos'])
            c['total_clics']         = stats.get('clickers', c['total_clics'])
            c['ctr']                 = round(c['clics_unicos'] / deliv * 100, 2) if deliv else c['ctr']
            c['click_to_open_rate']  = round(c['clics_unicos'] / c['aperturas_unicas'] * 100, 2) if c['aperturas_unicas'] else c['click_to_open_rate']
            c['cancelaciones_pct']   = round(stats.get('unsubscriptions', 0) / deliv * 100, 2) if deliv else c['cancelaciones_pct']
            c['spam']                = stats.get('complaints', c['spam'])
            c['asunto']              = remote.get('subject', c.get('asunto', ''))
            updated.append(c['mes'])
        except Exception as e:
            errors.append({'mes': c.get('mes'), 'error': str(e)})
    save_data(campaigns)
    return jsonify({'updated': updated, 'errors': errors})

# PDF upload
@app.route('/api/upload', methods=['POST'])
def upload_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'File must be a PDF'}), 400
    filepath = os.path.join(UPLOAD_DIR, file.filename)
    file.save(filepath)
    try:
        parsed = parse_pdf(filepath)
    except Exception as e:
        return jsonify({'error': f'Error parsing PDF: {e}'}), 500
    campaigns = load_data()
    if parsed['id'] in [c['id'] for c in campaigns]:
        return jsonify({'error': f'Ya existe la campaña "{parsed["id"]}"', 'parsed': parsed}), 409
    campaigns.append(parsed)
    campaigns.sort(key=lambda x: x.get('fecha_envio', ''))
    save_data(campaigns)
    return jsonify({'success': True, 'campaign': parsed})

@app.route('/api/campaigns/<campaign_id>', methods=['DELETE'])
def delete_campaign(campaign_id):
    campaigns = [c for c in load_data() if c['id'] != campaign_id]
    save_data(campaigns)
    return jsonify({'success': True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    app.run(debug=False, host='0.0.0.0', port=port)
