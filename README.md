# Projekt-Setup

Diese Anleitung beschreibt, wie du das Projekt lokal einrichtest und startklar machst.

## Voraussetzungen

- [Git](https://git-scm.com/downloads)
- [Visual Studio Code](https://code.visualstudio.com/)
- [Python 3.12.x](https://www.python.org/downloads/)

---

## Installation

### 1. Repository lokal klonen

```bash
git clone <REPO-URL>
cd <REPO-ORDNER>
```

### 2. Git installieren (falls noch nicht vorhanden)

Prüfen, ob Git installiert ist:

```bash
git --version
```

Falls nicht, Git von [git-scm.com](https://git-scm.com/downloads) herunterladen und installieren.

### 3. Git-Extension in VS Code installieren

In VS Code den Extensions-Tab öffnen (`Strg + Shift + X`) und nach einer Git-Extension suchen (z. B. **Git Extension Pack** oder **GitLens**), anschließend installieren.

### 4. Python 3.12.x installieren

Es wird **Python 3.12.x** benötigt. Version prüfen:

```bash
python --version
```

### 5. Virtuelle Umgebung erstellen (`.venv`)

**Windows (PowerShell):**

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
```

(Bei macOs vllt. anders) 

>  Wenn die Umgebung aktiv ist, steht `(.venv)` vor der Eingabezeile.

> Falls PowerShell die Aktivierung blockiert, einmalig ausführen:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

### 6. `.env`-Datei erstellen

Lege im Projektordner eine Datei namens `.env` an und trage deine Zugangsdaten ein:

```env
ANTHROPIC_API_KEY=...
ERPNEXT_URL=https://grp01.pia-web.ris.uni-due.de
ERPNEXT_API_KEY=...
ERPNEXT_API_SECRET=...
N8N_WEBHOOK_URL=...
```

### 7. Dependencies installieren

Mit aktivierter virtueller Umgebung (PowerShell):

```powershell
python -m pip install pipreqs
python -m pipreqs.pipreqs . --force --ignore .venv
python -m pip install -r requirements.txt
```

| Befehl | Zweck |
|--------|-------|
| `pip install pipreqs` | Installiert das Tool zum Erzeugen der `requirements.txt` |
| `pipreqs . --force --ignore .venv` | Erstellt die `requirements.txt` anhand der Imports im Code (überschreibt vorhandene Datei, ignoriert `.venv`) |
| `pip install -r requirements.txt` | Installiert alle benötigten Pakete |

---

##  Fertig!

