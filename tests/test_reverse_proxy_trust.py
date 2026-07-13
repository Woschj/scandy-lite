"""
Regressionstest für die Reverse-Proxy-Vertrauensstellung in app/main.py:
X-Forwarded-For darf das Rate-Limiting in auth.py NUR beeinflussen, wenn die
Verbindung tatsächlich vom Caddy-Container kommt - sonst könnte ein
beliebiger direkter Client per Header das Rate-Limiting umgehen/fälschen,
UND umgekehrt würde ohne diese Unterscheidung jeder über Caddy laufende
Request (zwingend für Kamera-Scan) fälschlich als eine einzige "IP" zählen.
"""
from app import main as main_module
from app.routers import auth as auth_module


async def test_forwarded_for_ignored_when_peer_not_trusted(client):
    auth_module._failed_logins.clear()
    main_module._trusted_proxy_ips = set()

    resp = await client.post(
        "/auth/login",
        data={"username": "does-not-exist", "password": "wrong"},
        headers={"X-Forwarded-For": "203.0.113.1"},
    )
    assert resp.status_code == 401
    assert "203.0.113.1" not in auth_module._failed_logins
    assert len(auth_module._failed_logins) == 1


async def test_forwarded_for_honored_only_when_peer_is_trusted_proxy(client):
    auth_module._failed_logins.clear()
    main_module._trusted_proxy_ips = set()

    # Erst ohne Vertrauen: echte Peer-Adresse ermitteln (unabhängig davon,
    # was der Test-Client als Peer nutzt).
    resp = await client.post(
        "/auth/login",
        data={"username": "does-not-exist", "password": "wrong"},
        headers={"X-Forwarded-For": "192.0.2.9"},
    )
    assert resp.status_code == 401
    assert len(auth_module._failed_logins) == 1
    real_peer = next(iter(auth_module._failed_logins))
    auth_module._failed_logins.clear()

    try:
        main_module._trusted_proxy_ips = {real_peer}
        resp = await client.post(
            "/auth/login",
            data={"username": "does-not-exist", "password": "wrong"},
            headers={"X-Forwarded-For": "198.51.100.7"},
        )
        assert resp.status_code == 401
        assert "198.51.100.7" in auth_module._failed_logins
        assert real_peer not in auth_module._failed_logins
    finally:
        main_module._trusted_proxy_ips = set()
        auth_module._failed_logins.clear()
