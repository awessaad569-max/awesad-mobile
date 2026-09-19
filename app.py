import os
import sqlite3
import requests
import datetime
from flask import Flask, render_template_string, request, send_file, redirect, url_for
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = Flask(__name__)

# --- إعدادات Supabase ---
SUPABASE_URL = "https://klfezzqwyropkucaigwb.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtsZmV6enF3eXJvcGt1Y2FpZ3diIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODk1OTMzODIsImV4cCI6MjEwNTE2OTM4Mn0.NaGX2PrbVx8prMDLP0JlSiYCU6_NEgw9aFd7eyc30SI"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# --- تهيئة قاعدة البيانات المحلية (SQLite) للعمل في حالة غياب الإنترنت ---
def init_local_db():
    conn = sqlite3.connect("local_awesad.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS local_invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT,
            total REAL,
            paiement_type TEXT,
            date TEXT,
            synced INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS local_caisse (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            type TEXT,
            montant REAL,
            description TEXT,
            synced INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

init_local_db()

# --- دوال التعامل مع Supabase مع دعم وضع الـ Offline ---
def sb_get(table, query=""):
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}?{query}"
        res = requests.get(url, headers=HEADERS, timeout=3)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

def sb_post(table, data):
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}"
        res = requests.post(url, headers=HEADERS, json=data, timeout=3)
        return res.status_code in (200, 201)
    except Exception:
        # إذا قصت الإنترنت، نخزنو البيانات محلياً باش ما تضيعش
        conn = sqlite3.connect("local_awesad.db")
        cursor = conn.cursor()
        if table == "invoices":
            cursor.execute("INSERT INTO local_invoices (client_name, total, paiement_type, date, synced) VALUES (?, ?, ?, ?, 0)",
                           (data.get("client_name"), data.get("total"), data.get("paiement_type"), data.get("date")))
        elif table == "caisse":
            cursor.execute("INSERT INTO local_caisse (date, type, montant, description, synced) VALUES (?, ?, ?, ?, 0)",
                           (data.get("date"), data.get("type"), data.get("montant"), data.get("description")))
        conn.commit()
        conn.close()
        return False

def sb_patch(table, query, data):
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}?{query}"
        res = requests.patch(url, headers=HEADERS, json=data, timeout=3)
        return res.status_code in (200, 204)
    except Exception:
        return False

def sb_delete(table, query):
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}?{query}"
        res = requests.delete(url, headers=HEADERS, timeout=3)
        return res.status_code in (200, 204)
    except Exception:
        return False

# --- قوالب HTML للواجهات ---
BASE_HTML = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>AWESAD Mobile Pro</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; background: #f4f6f9; padding: 10px; margin: 0; }
        .container { max-width: 600px; margin: auto; background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        h2, h3 { text-align: center; color: #2c3e50; }
        nav { display: flex; justify-content: space-around; background: #2c3e50; padding: 10px; border-radius: 5px; margin-bottom: 15px; }
        nav a { color: white; text-decoration: none; font-weight: bold; font-size: 13px; }
        nav a:hover { color: #2ecc71; }
        label { font-weight: bold; display: block; margin-top: 8px; font-size: 13px; }
        select, input, button { width: 100%; padding: 8px; margin-top: 4px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; font-size: 14px; }
        button { background: #2ecc71; color: white; font-weight: bold; border: none; margin-top: 15px; cursor: pointer; }
        button:hover { background: #27ae60; }
        .btn-danger { background: #e74c3c; }
        .btn-danger:hover { background: #c0392b; }
        .btn-warning { background: #f39c12; }
        .btn-warning:hover { background: #d35400; }
        .btn-pdf { display: block; text-align: center; background: #3498db; color: white; padding: 10px; border-radius: 4px; text-decoration: none; font-weight: bold; margin-top: 10px; }
        .alert { background: #d4edda; color: #155724; padding: 8px; border-radius: 4px; margin-bottom: 10px; text-align: center; font-weight: bold; font-size: 13px; }
        table { width: 100%; margin-top: 10px; border-collapse: collapse; font-size: 12px; }
        th, td { border: 1px solid #ddd; padding: 5px; text-align: center; }
        th { background: #2c3e50; color: white; }
        .actions { display: flex; gap: 5px; justify-content: center; }
    </style>
</head>
<body>
    <div class="container">
        <h2>SOCIETE AWESAD</h2>
        <nav>
            <a href="/">🧾 Factures</a>
            <a href="/stock">📦 Stock</a>
            <a href="/transfer">🔄 Transfert</a>
            <a href="/bonsortie">📋 Bon de Sortie</a>
        </nav>
        CONTENT_PLACEHOLDER
    </div>
</body>
</html>
"""

def render_page(content_html, **context):
    full_html = BASE_HTML.replace("CONTENT_PLACEHOLDER", content_html)
    return render_template_string(full_html, **context)

@app.route('/', methods=['GET', 'POST'])
def index():
    pdf_filename = None
    if request.method == 'POST':
        try:
            client_id = request.form.get('client_id')
            article_id = int(request.form.get('article_id'))
            qty = float(request.form.get('qty'))
            source = request.form.get('source')
            paiement = request.form.get('paiement')

            cname = "Client Divers"
            if client_id:
                res_c = sb_get("clients", f"id=eq.{client_id}&select=*")
                if res_c:
                    cname = res_c[0].get("name", "Client Divers")

            res_art = sb_get("articles", f"id=eq.{article_id}&select=*")
            if res_art:
                art = res_art[0]
                current_stock = float(art.get(source) or 0)
                price = float(art.get("prix_vente") or 0)
                
                if client_id:
                    res_p = sb_get("client_prices", f"client_id=eq.{client_id}&article_id=eq.{article_id}&select=*")
                    if res_p:
                        price = float(res_p[0].get("special_price") or price)

                total = price * qty
                sb_patch("articles", f"id=eq.{article_id}", {source: current_stock - qty})

                today = str(datetime.date.today())
                sb_post("invoices", {
                    "client_name": cname,
                    "total": total,
                    "paiement_type": paiement,
                    "date": today
                })

                if "Comptant" in paiement:
                    sb_post("caisse", {
                        "date": today,
                        "type": "Entrée",
                        "montant": total,
                        "description": f"Vente Mobile - Client: {cname} (Art: {art.get('name')})"
                    })

                pdf_filename = f"Facture_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                c = canvas.Canvas(pdf_filename, pagesize=letter)
                c.setFont("Helvetica-Bold", 18)
                c.drawString(50, 750, "SOCIETE AWESAD DE COMMERCE")
                c.setFont("Helvetica", 10)
                c.drawString(50, 735, "Matériel Agricole, Irrigation & Composants Techniques")
                c.line(50, 725, 550, 725)
                
                c.setFont("Helvetica-Bold", 14)
                c.drawString(50, 690, f"FACTURE PRO ({paiement})")
                c.setFont("Helvetica", 11)
                c.drawString(50, 660, f"Client : {cname}")
                c.drawString(50, 640, f"Date : {today}")
                
                c.rect(50, 580, 500, 30, fill=1, stroke=0)
                c.setFillColorRGB(1, 1, 1)
                c.setFont("Helvetica-Bold", 10)
                c.drawString(60, 590, "Désignation Article")
                c.drawString(250, 590, "Quantité")
                c.drawString(350, 590, "Prix Unitaire")
                c.drawString(450, 590, "Total (DT)")
                
                c.setFillColorRGB(0, 0, 0)
                c.setFont("Helvetica", 10)
                c.drawString(60, 550, str(art.get("name")))
                c.drawString(250, 550, str(qty))
                c.drawString(350, 550, f"{price:.3f}")
                c.drawString(450, 550, f"{total:.3f}")
                
                c.line(50, 520, 550, 520)
                c.setFont("Helvetica-Bold", 12)
                c.drawString(350, 490, f"TOTAL À PAYER : {total:.3f} DT")
                c.save()

        except Exception as e:
            print("Erreur:", e)

    clients = sb_get("clients", "select=*")
    articles = sb_get("articles", "select=*")
    invoices = sb_get("invoices", "select=*")

    content = """
    <h3>Créer une Facture Pro (Mode Connecté / Hors Ligne)</h3>
    {% if pdf_file %}
        <div class="alert">Facture créée, stock déduit et PDF prêt ! (En cas de coupure réseau, les données sont sauvegardées en local)</div>
        <a class="btn-pdf" href="/download_invoice/{{ pdf_file }}" target="_blank">📥 Ouvrir / Imprimer la Facture PDF</a>
        <br>
        <a href="/" style="display:block; text-align:center; color:#555; text-decoration:none; margin-top:5px; font-weight:bold;">← Créer une autre facture</a>
    {% else %}
        <form method="POST">
            <label>Client :</label>
            <select name="client_id">
                <option value="">-- Client Divers --</option>
                {% for c in clients %}
                <option value="{{ c.id }}">{{ c.name }}</option>
                {% endfor %}
            </select>

            <label>Article :</label>
            <select name="article_id" required>
                <option value="">-- Choisir Article --</option>
                {% for a in articles %}
                <option value="{{ a.id }}">{{ a.name }} (Dépôt: {{ a.stock_depot }} | Magasin: {{ a.stock_magasin }})</option>
                {% endfor %}
            </select>

            <label>Quantité :</label>
            <input type="number" name="qty" value="1" min="1" required>

            <label>Source Stock :</label>
            <select name="source">
                <option value="stock_magasin">Magasin</option>
                <option value="stock_depot">Dépôt</option>
            </select>

            <label>Mode de Paiement :</label>
            <select name="paiement">
                <option value="Comptant (Espèce)">Comptant (Espèce)</option>
                <option value="Crédit">Crédit</option>
            </select>

            <button type="submit">Valider & Générer Facture</button>
        </form>

        <h3 style="margin-top:20px;">Dernières Factures</h3>
        <table>
            <tr>
                <th>Client</th>
                <th>Total</th>
                <th>Paiement</th>
                <th>PDF</th>
            </tr>
            {% for inv in invoices[-5:]|reverse %}
            <tr>
                <td>{{ inv.client_name }}</td>
                <td>{{ inv.total }} DT</td>
                <td>{{ inv.paiement_type }}</td>
                <td><a href="/print_invoice/{{ inv.id }}" target="_blank" style="color:#3498db; font-weight:bold;">🖨️ PDF</a></td>
            </tr>
            {% endfor %}
        </table>
    {% endif %}
    """
    return render_page(content, clients=clients, articles=articles, invoices=invoices, pdf_file=pdf_filename)

@app.route('/download_invoice/<filename>')
def download_invoice(filename):
    return send_file(filename, as_attachment=True)

@app.route('/print_invoice/<inv_id>')
def print_invoice(inv_id):
    res = sb_get("invoices", f"id=eq.{inv_id}&select=*")
    if not res: return "Facture introuvable"
    inv = res[0]
    
    filename = f"Facture_{inv['id']}.pdf"
    c = canvas.Canvas(filename, pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 750, "SOCIETE AWESAD DE COMMERCE")
    c.setFont("Helvetica", 10)
    c.drawString(50, 735, "Facture Pro")
    c.drawString(50, 710, f"Client : {inv['client_name']}")
    c.drawString(50, 695, f"Date : {inv['date']}")
    c.drawString(50, 680, f"Total : {inv['total']} DT")
    c.save()
    return send_file(filename, as_attachment=True)

@app.route('/stock', methods=['GET', 'POST'])
def stock():
    if request.method == 'POST':
        action = request.form.get('action')
        name = request.form.get('name')
        depot = float(request.form.get('stock_depot') or 0)
        magasin = float(request.form.get('stock_magasin') or 0)
        p_achat = float(request.form.get('prix_achat') or 0)
        p_vente = float(request.form.get('prix_vente') or 0)
        
        if action == 'add':
            sb_post("articles", {"name": name, "stock_depot": depot, "stock_magasin": magasin, "prix_achat": p_achat, "prix_vente": p_vente, "min_alert": 5})
        elif action == 'edit':
            aid = request.form.get('id')
            sb_patch("articles", f"id=eq.{aid}", {"name": name, "stock_depot": depot, "stock_magasin": magasin, "prix_achat": p_achat, "prix_vente": p_vente})
        elif action == 'delete':
            aid = request.form.get('id')
            sb_delete("articles", f"id=eq.{aid}")
        return redirect(url_for('stock'))

    articles = sb_get("articles", "select=*")
    edit_art = None
    edit_id = request.args.get('edit_id')
    if edit_id:
        res = sb_get("articles", f"id=eq.{edit_id}&select=*")
        if res: edit_art = res[0]

    content = """
    <h3>Gestion du Stock (Dépôt & Magasin)</h3>
    <form method="POST">
        <input type="hidden" name="action" value="{{ 'edit' if edit_art else 'add' }}">
        {% if edit_art %}<input type="hidden" name="id" value="{{ edit_art.id }}">{% endif %}
        
        <label>Nom Article :</label>
        <input type="text" name="name" value="{{ edit_art.name if edit_art else '' }}" required>
        
        <label>Stock Dépôt :</label>
        <input type="number" step="any" name="stock_depot" value="{{ edit_art.stock_depot if edit_art else 0 }}" required>
        
        <label>Stock Magasin :</label>
        <input type="number" step="any" name="stock_magasin" value="{{ edit_art.stock_magasin if edit_art else 0 }}" required>
        
        <label>Prix Achat :</label>
        <input type="number" step="any" name="prix_achat" value="{{ edit_art.prix_achat if edit_art else 0 }}">
        
        <label>Prix Vente :</label>
        <input type="number" step="any" name="prix_vente" value="{{ edit_art.prix_vente if edit_art else 0 }}" required>
        
        <button type="submit">{{ 'Modifier Article' if edit_art else 'Ajouter Article' }}</button>
    </form>

    <a href="/print_stock_pdf" target="_blank" class="btn-pdf" style="background:#27ae60; margin-top:15px;">🖨️ Imprimer Rapport Stock PDF (Tableau)</a>

    <table>
        <tr>
            <th>Article</th>
            <th>Dépôt</th>
            <th>Magasin</th>
            <th>P. Vente</th>
            <th>Actions</th>
        </tr>
        {% for a in articles %}
        <tr>
            <td>{{ a.name }}</td>
            <td>{{ a.stock_depot }}</td>
            <td>{{ a.stock_magasin }}</td>
            <td>{{ a.prix_vente }} DT</td>
            <td class="actions">
                <a href="/stock?edit_id={{ a.id }}" class="btn-warning" style="padding:3px 6px; color:white; text-decoration:none; border-radius:3px;">Modifier</a>
                <form method="POST" style="display:inline;" onsubmit="return confirm('Supprimer cet article ?');">
                    <input type="hidden" name="action" value="delete">
                    <input type="hidden" name="id" value="{{ a.id }}">
                    <button type="submit" class="btn-danger" style="margin:0; padding:3px 6px; width:auto;">Supprimer</button>
                </form>
            </td>
        </tr>
        {% endfor %}
    </table>
    """
    return render_page(content, articles=articles, edit_art=edit_art)

@app.route('/print_stock_pdf')
def print_stock_pdf():
    articles = sb_get("articles", "select=*")
    filename = "Inventaire_Stock.pdf"
    c = canvas.Canvas(filename, pagesize=letter)
    
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 750, "SOCIETE AWESAD DE COMMERCE")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 730, "Rapport d'Inventaire Stock (Dépôt & Magasin)")
    c.setFont("Helvetica", 10)
    c.drawString(50, 715, f"Date : {datetime.date.today()}")
    c.line(50, 705, 550, 705)
    
    y = 675
    c.setFillColorRGB(0.17, 0.24, 0.31)
    c.rect(50, y - 5, 500, 20, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, y, "Désignation Article")
    c.drawString(320, y, "Stock Dépôt")
    c.drawString(430, y, "Stock Magasin")
    
    y -= 25
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 10)
    
    for a in articles:
        if y < 50:
            c.showPage()
            y = 750
        c.drawString(60, y, str(a.get('name', '')))
        c.drawString(320, y, str(a.get('stock_depot', 0)))
        c.drawString(430, y, str(a.get('stock_magasin', 0)))
        
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.line(50, y - 5, 550, y - 5)
        y -= 20
        
    c.save()
    return send_file(filename, as_attachment=True)

@app.route('/transfer', methods=['GET', 'POST'])
def transfer():
    if request.method == 'POST':
        aid = int(request.form.get('article_id'))
        qty = float(request.form.get('qty'))
        sens = request.form.get('sens')
        
        res = sb_get("articles", f"id=eq.{aid}&select=*")
        if res:
            art = res[0]
            depot = float(art.get("stock_depot") or 0)
            mag = float(art.get("stock_magasin") or 0)
            
            if sens == "depot_to_magasin":
                if depot >= qty:
                    sb_patch("articles", f"id=eq.{aid}", {"stock_depot": depot - qty, "stock_magasin": mag + qty})
            else:
                if mag >= qty:
                    sb_patch("articles", f"id=eq.{aid}", {"stock_depot": depot + qty, "stock_magasin": mag - qty})
        return redirect(url_for('transfer'))

    articles = sb_get("articles", "select=*")
    content = """
    <h3>Transfert de Stock (Dépôt ⇄ Magasin)</h3>
    <form method="POST">
        <label>Article :</label>
        <select name="article_id" required>
            {% for a in articles %}
            <option value="{{ a.id }}">{{ a.name }} (Dépôt: {{ a.stock_depot }} | Magasin: {{ a.stock_magasin }})</option>
            {% endfor %}
        </select>

        <label>Sens du Transfert :</label>
        <select name="sens">
            <option value="depot_to_magasin">Dépôt ➔ Magasin</option>
            <option value="magasin_to_depot">Magasin ➔ Dépôt</option>
        </select>

        <label>Quantité :</label>
        <input type="number" step="any" name="qty" min="0.1" required>

        <button type="submit">Valider le Transfert</button>
    </form>
    """
    return render_page(content, articles=articles)

@app.route('/bonsortie', methods=['GET', 'POST'])
def bonsortie():
    pdf_filename = None
    if request.method == 'POST':
        articles = sb_get("articles", "select=*")
        pdf_filename = f"Bon_Sortie_Magasin_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        c = canvas.Canvas(pdf_filename, pagesize=letter)
        
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 750, "SOCIETE AWESAD DE COMMERCE")
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, 730, "BON DE SORTIE / ETAT STOCK MAGASIN")
        c.setFont("Helvetica", 10)
        c.drawString(50, 715, f"Date : {datetime.date.today()}")
        c.line(50, 705, 550, 705)
        
        y = 675
        c.setFillColorRGB(0.17, 0.24, 0.31)
        c.rect(50, y - 5, 500, 20, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(60, y, "Désignation Article")
        c.drawString(380, y, "Stock Magasin Disponible")
        
        y -= 25
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 10)
        
        for a in articles:
            stock_mag = float(a.get('stock_magasin') or 0)
            if stock_mag > 0:
                if y < 50:
                    c.showPage()
                    y = 750
                c.drawString(60, y, str(a.get('name', '')))
                c.drawString(380, y, str(stock_mag))
                
                c.setStrokeColorRGB(0.8, 0.8, 0.8)
                c.line(50, y - 5, 550, y - 5)
                y -= 20
                
        c.save()

    content = """
    <h3>Bon de Sortie / État du Stock Magasin</h3>
    {% if pdf_filename %}
        <div class="alert">Bon de sortie (Stock Magasin) généré avec succès !</div>
        <a href="/download_bs/{{ pdf_filename }}" target="_blank" class="btn-pdf">📥 Télécharger / Imprimer Bon de Sortie (Sans Prix)</a>
    {% endif %}
    <form method="POST">
        <p style="font-size:13px; color:#555; text-align:center; margin-bottom:15px;">
            En cliquant sur le bouton ci-dessous, un bon récapitulatif de tout le stock disponible en magasin sera généré sous forme de tableau (sans prix).
        </p>
        <button type="submit">Générer le Bon de Sortie (Stock Magasin)</button>
    </form>
    """
    return render_page(content, pdf_filename=pdf_filename)

@app.route('/download_bs/<filename>')
def download_bs(filename):
    return send_file(filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

