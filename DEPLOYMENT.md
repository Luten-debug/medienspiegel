# Medienspiegel - Deployment & Nutzung

## Empfehlung

| Szenario | Empfehlung | Kosten |
|----------|------------|--------|
| Nur fuer dich | **Lokal starten** (Option 1) | Kostenlos |
| 2-5 Kollegen im Buero | **Lokales Netzwerk** (Option 2) | Kostenlos |
| Oeffentlich, testen | **Render.com Free** (Option 3) | Kostenlos |
| Oeffentlich, zuverlaessig | **Render.com Starter** (Option 3) | $7/Monat |

---

## Option 1: Lokal auf Mac/PC (einfachste Variante)

### Voraussetzungen
- Python 3.9+ (`python3 --version`)
- pip (`pip3 --version`)

### Installation & Start

```bash
cd medienspiegel
pip3 install -r requirements.txt
python3 run.py
```

Die App laeuft auf **http://localhost:5050**

### Autostart

**Mac:** Erstelle `start_medienspiegel.command`:
```bash
#!/bin/bash
cd /pfad/zu/medienspiegel
python3 run.py
```
Dann: `chmod +x start_medienspiegel.command` und in Systemeinstellungen > Anmeldeobjekte hinzufuegen.

**Windows:** Erstelle `start.bat`:
```batch
cd C:\pfad\zu\medienspiegel
python run.py
```
In Autostart-Ordner legen (`Win+R` > `shell:startup`).

---

## Option 2: Im lokalen Netzwerk fuer Kollegen

Die App ist bereits fuer Netzwerkzugriff konfiguriert (0.0.0.0).

```bash
python3 run.py
```

Kollegen im gleichen WLAN/Netzwerk koennen zugreifen ueber:
**http://DEINE-IP:5050** (z.B. http://192.168.1.100:5050)

IP herausfinden:
```bash
# Mac:
ipconfig getifaddr en0
# Windows:
ipconfig    # -> "IPv4 Address" suchen
```

### Stabiler mit Gunicorn

```bash
pip3 install gunicorn
gunicorn -w 2 -b 0.0.0.0:5050 "app:create_app()"
```

### Hinweise
- Nur im gleichen Netzwerk erreichbar
- Dein Rechner muss eingeschaltet sein
- Firewall: Port 5050 freigeben (Mac: Systemeinstellungen > Firewall)

---

## Option 3: Render.com (oeffentlich erreichbar)

### 1. Code auf GitHub

```bash
cd medienspiegel
git init
echo -e "config.yaml\ndata/\n__pycache__/\n*.pyc\n.env" > .gitignore
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/DEIN-USER/medienspiegel.git
git push -u origin main
```

### 2. Auf Render deployen

1. Gehe zu **render.com** > "New" > "Web Service"
2. GitHub Repo verbinden
3. Einstellungen:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn -w 2 -b 0.0.0.0:$PORT "app:create_app()"`
   - **Region:** Frankfurt (EU)
4. Environment Variable: `ANTHROPIC_API_KEY` = dein Key
5. "Create Web Service"

### Kosten & Limits
- **Free:** App schlaeft nach 15 Min (Kaltstart ~30s), DB wird bei Deploy resettet
- **Starter ($7/Monat):** Immer aktiv + Persistent Disk fuer DB

---

## Option 4: PythonAnywhere ($5/Monat)

1. Account auf **pythonanywhere.com**
2. Bash-Terminal: `git clone` + `pip install -r requirements.txt`
3. Web-App erstellen > Flask > WSGI-Datei:
```python
import sys
sys.path.insert(0, '/home/DEIN-USER/medienspiegel')
from app import create_app
application = create_app()
```
4. Static Files: URL `/static/` -> `/home/DEIN-USER/medienspiegel/app/static/`

SQLite funktioniert hier persistent.

---

## Datenbank-Backup

```bash
cp data/medienspiegel.db data/backup_$(date +%Y%m%d).db
```

## Sicherheit

- `config.yaml` enthaelt den API-Key - NICHT in oeffentliche Git-Repos!
- `.gitignore` muss `config.yaml` und `data/` enthalten
- Fuer Cloud: API-Key als Umgebungsvariable setzen
