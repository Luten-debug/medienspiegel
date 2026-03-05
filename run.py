#!/usr/bin/env python3
"""Medienspiegel - Giga Factory Berlin-Brandenburg Media Monitor."""

from app import create_app

app = create_app()

if __name__ == '__main__':
    print("\n  Medienspiegel laeuft auf http://localhost:5050\n")
    app.run(debug=True, host='0.0.0.0', port=5050)
