"""
QR-Code-Erzeugung für Mitarbeiterausweise (siehe app/routers/badge.py).

Als Data-URI direkt ins Template eingebettet statt über eine eigene
Static-/Upload-Route ausgeliefert: Ausweise werden selten genug aufgerufen,
dass das Neu-Rendern pro Request keine Rolle spielt, und es braucht dadurch
keine Datei auf Platte, keinen Cache-Invalidierungs-Fall (Barcode ändert
sich -> altes Bild wäre sonst noch unter derselben URL erreichbar).
"""
import base64
from io import BytesIO

import qrcode


def qr_data_uri(data: str) -> str:
    img = qrcode.make(data, box_size=10, border=2)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
