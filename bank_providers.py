"""Erweiterungspunkt für bankabhängige Adapter, ohne Zugangsdaten im Frontend."""
from dataclasses import dataclass
from typing import Protocol

@dataclass
class BankTransaction:
    external_id: str
    date: str  # ISO YYYY-MM-DD
    merchant: str
    amount_cents: int  # Ausgaben positiv, Gutschriften negativ
    currency: str = 'EUR'

class BankProvider(Protocol):
    def authorize(self) -> str:
        """Autorisierungs-URL liefern; Secrets im macOS-Schlüsselbund speichern."""
        ...

    def fetch_transactions(self, since: str) -> list[BankTransaction]:
        """Stabile externe IDs liefern; keine Bank-Passwörter in SQLite speichern."""
        ...

class UnconfiguredProvider:
    def authorize(self):
        raise NotImplementedError('Bankadapter noch nicht eingerichtet. CSV-Import ist verfügbar.')

    def fetch_transactions(self, since):
        raise NotImplementedError('Hier den bankabhängigen Adapter implementieren.')
