"""Regression test for a real bug found during Day 3 frontend integration:
the API had no CORS configuration, so a real browser blocked every request
from the Vite dev server (a different origin) even though curl/pytest never
notice, since browsers enforce CORS and HTTP clients don't.
"""


def test_frontend_origin_is_allowed_by_cors(client):
    response = client.options(
        "/api/claims",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
