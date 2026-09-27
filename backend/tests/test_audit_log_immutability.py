"""Covers Day 2 acceptance item S: preservation logs cannot be updated or
deleted through the API. There is no PUT/PATCH/DELETE route registered at
all for preservation-log or timeline — FastAPI returns 405 automatically
for any method that isn't registered on an existing path.
"""


def test_no_mutating_routes_registered_for_preservation_log():
    from app.main import app

    for route in app.routes:
        if "preservation-log" in route.path or "timeline" in route.path:
            assert route.methods <= {"GET", "HEAD", "OPTIONS"}, f"{route.path} allows {route.methods}"


def test_put_and_delete_on_preservation_log_return_405(client, demo_claim):
    assert client.put(f"/api/claims/{demo_claim}/preservation-log").status_code == 405
    assert client.delete(f"/api/claims/{demo_claim}/preservation-log").status_code == 405


def test_put_and_delete_on_timeline_return_405(client, demo_claim):
    assert client.put(f"/api/claims/{demo_claim}/timeline").status_code == 405
    assert client.delete(f"/api/claims/{demo_claim}/timeline").status_code == 405
