import os
import requests
import datetime
from flask import Flask, render_template_string, request, send_file
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

def sb_get(table, query=""):
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}?{query}"
        res = requests.get(url, headers=HEADERS)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

# قالب HTML لعرض الواجهة وتونسة الستوك والحريف الحقيقي
HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>AWESAD - Mobile ERP Pro</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; background: #f4f6f9; padding: 15px; margin: 0; }
        .container { max-width: 500px; margin: auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        h2 { text-align: center; color: #2c3e50; }
        label { font-weight: bold; display: block; margin-top: 10px; }
        select, input, button { width: 100%; padding: 10px; margin-top: 5px; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; }
        button { background: #2ecc71; color: white; font-size: 16px; font-weight: bold; border: none; margin-top: 20px; cursor: pointer; }
        button:hover { background: #27ae60; }
        .alert { background: #d4edda; color: #155724; padding: 10px; border-radius: 5px; margin-bottom: 15px; text-align: center; font-weight: bold; }
        .btn-pdf { display: block; text-align: center; background: #3498db; color: white; padding: 12px; border-radius: 5px; text-decoration: none; font-weight: bold; margin-top: 15px; }
        .btn-pdf:hover { background: #2980b9; }
        .stock-info { background: #e9ecef; padding: 10px; margin-top: 20px; border-radius: 5px; font-size: 13px; }
        .stock-table { width: 100%; margin-top: 5px; border-collapse: collapse; }
        .stock-table th, .stock-table td { border: 1px solid #ddd; padding: 6px; text-align: center; }
        .stock-table th { background: #2c3e50; color: white; }
    </style>
</head>
<body>
    <div class="container">
        <h2>AWESAD MOBILE</h2>
        {% if pdf_file %}
            <div class="alert">Facture créée, stock déduit et caisse mise à jour !</div>
            <p style="text-align:center;">Cliquez ci-dessous pour ouvrir et imprimer la facture PDF :</p>
            <a class="btn-pdf" href="/download_invoice/{{ pdf_file }}" target="_blank">📥 Ouvrir / Imprimer la Facture PDF</a>
            <br>
            <a href="/" style="display:block; text-align:center; color:#555; text-decoration:none; margin-top:10px;">← Créer une autre facture</a>
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

            <div class="stock-info">
                <strong>📊 Aperçu du Stock Actuel :</strong>
                <table class="stock-table">
                    <tr>
                        <th>Article</th>
                        <th>Dépôt</th>
                        <th>Magasin</th>
                        <th>P. Vente</th>
                    </tr>
                    {% for a in articles %}
                    <tr>
                        <td>{{ a.name }}</td>
                        <td>{{ a.stock_depot }}</td>
                        <td>{{ a.stock_magasin }}</td>
                        <td>{{ a.prix_vente }} DT</td>
                    </tr>
                    {% endfor %}
                </table>
            </div>
        {% endif %}
    </div>
</body>
</html>
"""

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

            # جلب اسم الحريف الحقيقي إذا تم اختياره
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
                
                # التحقق من وجود سعر خاص بالحريف
                if client_id:
                    res_p = sb_get("client_prices", f"client_id=eq.{client_id}&article_id=eq.{article_id}&select=*")
                    if res_p:
                        price = float(res_p[0].get("special_price") or price)

                total = price * qty

                # خصم المخزون
                requests.patch(f"{SUPABASE_URL}/rest/v1/articles?id=eq.{article_id}", headers=HEADERS, json={source: current_stock - qty})

                # تسجيل الفاتورة بالاسم الحقيقي للحريف
                today = str(datetime.date.today())
                requests.post(f"{SUPABASE_URL}/rest/v1/invoices", headers=HEADERS, json={
                    "client_name": cname,
                    "total": total,
                    "paiement_type": paiement,
                    "date": today
                })

                # تسجيل الصندوق إذا كان كاش
                if "Comptant" in paiement:
                    requests.post(f"{SUPABASE_URL}/rest/v1/caisse", headers=HEADERS, json={
                        "date": today,
                        "type": "Entrée",
                        "montant": total,
                        "description": f"Vente Mobile - Client: {cname} (Art ID: {article_id})"
                    })

                # إنشاء ملف الـ PDF بالفاتورة تحمل اسم الحريف الصحيح
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
    return render_template_string(HTML_LAYOUT, clients=clients, articles=articles, pdf_file=pdf_filename)

@app.route('/download_invoice/<filename>')
def download_invoice(filename):
    return send_file(filename, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

