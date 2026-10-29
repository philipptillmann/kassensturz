# Local development

The `local` branch contains the complete server web application, including
authentication, users, demo data, imports, charts, backups and the Shortcuts API.
It uses Tesseract instead of the original Mac-only Apple Vision OCR.
The native `android-standalone` app remains a separate project.

## Run directly with Python

Use Python 3.12 (the same version as the server container). From the repository
root, create a virtual environment and install the pinned dependencies once.

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\start.ps1
# Equivalent: .\.venv\Scripts\python.exe run_local.py
```

macOS / Linux:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run_local.py
```

On macOS, `start.command` also uses this virtual environment.
Open **http://localhost:8080**. Read the generated password from
`.local-data/login-password.txt` and use it for the initial/shared login. Named
users can then be managed through the app, as on the server.

The launcher binds only to `127.0.0.1`, retains authentication and CSRF checks,
and always stores databases, users, demo data and the local password under
`.local-data/` (ignored by Git). It ignores production `DATA_DIR`,
`APP_PASSWORD_FILE` and `PUBLIC_URL` settings and does not read `.env`.
Existing `data/` files and Docker server volumes are not used or migrated.
Select **Demo** in the app to experiment with fictional data.
Do not copy private production databases into the repository.

Stop with Ctrl+C. Restart after Python edits; reload the browser after static
file edits. There is no debugger or automatic reloader. To use another port:

```sh
python run_local.py --port 8081
```

Run that command with your virtual environment's Python. The local password and
data survive restarts. Edit the password file to change the shared password
(minimum 12 characters), then restart; existing shared-login sessions expire.

### Receipt OCR

Install Tesseract with both German (`deu`) and English (`eng`) language data and
make `tesseract` available on PATH before starting the app. Verify with
`tesseract --list-langs`. On Windows restart your terminal after changing PATH.
On macOS with Homebrew: `brew install tesseract tesseract-lang`.
On Debian/Ubuntu: `sudo apt install tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng`.
Other features can be developed without Tesseract; receipt recognition needs it.

## Optional Docker environment

This separate Compose project uses its own data volume, includes Tesseract and
exposes the app only on loopback. Set a separate development password:

```powershell
$env:LOCAL_APP_PASSWORD = 'choose-a-local-password-at-least-12-characters'
docker compose -f compose.local.yaml up --build
```

macOS / Linux:

```sh
export LOCAL_APP_PASSWORD='choose-a-local-password-at-least-12-characters'
docker compose -f compose.local.yaml up --build
```

Open http://localhost:8080 and log in with that password. Set `LOCAL_PORT=8081`
in the environment if port 8080 is occupied. Stop with Ctrl+C, then use
`docker compose -f compose.local.yaml down` to remove containers while retaining
data. Rebuild after source changes; source files are copied into the image.
The Docker volume and direct-Python `.local-data/` are independent.
Use this Compose file by itself, without the production Compose files.

## Checks to run locally

With dependencies installed, use the virtual environment's Python:

```sh
python -m unittest discover -s tests -v
```

Container-specific tests require the existing container setup; real OCR checks
need Tesseract and the language data. With Node.js installed:

```sh
node tests/test_charts.cjs
node --check static/app.js
node --check static/charts.js
node --check static/login.js
```

For manual acceptance: log in, switch to Demo, create/edit a split expense,
check charts and groups, preview a sample CSV, and export/restore a demo backup.
Restart and confirm the demo edits remain. Test OCR with a non-private receipt.
These are instructions for the developer; no hosted workflow is started.

## Keeping the branch current

Merge future `server` changes into `local`, retaining the local launcher and
configuration. Keep application and calculation code aligned with `server`.
This synchronization retains VERSION 0.13.0; it adds development configuration
without publishing a new server or Android app release.

### Verification of this synchronization

Python syntax checks and launcher help/invalid-port checks passed. The existing
13 ledger tests were attempted with Python 3.11 on Windows; all reported SQLite
file-lock errors during temporary-directory cleanup. They are not recorded as
passing. The full HTTP/OCR suite and browser acceptance have not run: this
checkout environment lacks Flask, Waitress, pillow-heif, Node.js and Docker.
Use the Python 3.12 setup above for further verification. The existing GitHub
workflow remains manual-only; no hosted build or deployment was started.
