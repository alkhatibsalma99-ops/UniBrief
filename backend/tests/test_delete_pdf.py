
from app.main import app

def test_delete_pdf_route_exists():
    fastapi_app = getattr(app, "app", app)

    routes = [
        route
        for route in fastapi_app.routes
        if getattr(route, "path", None)
        == "/projects/{project_id}/files/{file_id}"
        and "DELETE" in (
            getattr(route, "methods", None) or set()
        )
    ]

    assert len(routes) == 1


def test_delete_pdf_handler():
    fastapi_app = getattr(app, "app", app)

    routes = [
        route
        for route in fastapi_app.routes
        if getattr(route, "path", None)
        == "/projects/{project_id}/files/{file_id}"
        and "DELETE" in (
            getattr(route, "methods", None) or set()
        )
    ]

    assert len(routes) == 1
    assert routes[0].endpoint.__name__ == "delete_project_pdf"
