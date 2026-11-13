# Entry point pag local: python run.py. Gagamitin yung app
# factory para pareho sa ginagawa ng tests.
from app import create_app

app = create_app()

# Built-in dev server lang ito, debug kung naka-enable sa config.
if __name__ == "__main__":
    app.run(debug=app.config.get("DEBUG", False))
