"""Run the server application on loopback with isolated development data."""
import argparse
import os
from pathlib import Path
import secrets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')

    # Set before importing the ledger: DB is resolved at import time.
    data = Path(__file__).resolve().parent / '.local-data'
    data.mkdir(exist_ok=True)
    password_file = data / 'login-password.txt'
    if not password_file.exists():
        with password_file.open('x', encoding='utf-8') as stream:
            stream.write(secrets.token_urlsafe(24) + '\n')
        password_file.chmod(0o600)
    os.environ['DATA_DIR'] = str(data)
    os.environ['APP_PASSWORD_FILE'] = str(password_file)
    # Ignore production PUBLIC_URL; requests must use their own local origin.
    os.environ['PUBLIC_URL'] = ''
    os.environ['ALLOW_HTTP'] = '1'

    from server import create_app
    from waitress import serve
    import backups

    application = create_app()
    application.config['TRUSTED_HOSTS'] = ['localhost', '127.0.0.1']
    print(f'Open http://localhost:{args.port}', flush=True)
    print(f'Local login password is stored in {password_file}', flush=True)
    print('Use the Demo dataset for testing. Stop with Ctrl+C; restart after Python edits.', flush=True)
    serve(application, host='127.0.0.1', port=args.port, threads=8,
          max_request_body_size=backups.MAX_ARCHIVE_BYTES, channel_timeout=120,
          clear_untrusted_proxy_headers=True, expose_tracebacks=False)


if __name__ == '__main__':
    main()
