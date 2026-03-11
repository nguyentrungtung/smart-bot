# scripts/update_test_html.py
import jwt
import time
from pathlib import Path

def update():
    priv_path = Path(".keys/private_key.pem")
    if not priv_path.exists():
        print("Missing keys!")
        return

    priv = priv_path.read_text()
    token = jwt.encode(
        {
            "sub": "test_user_123",
            "name": "Test User",
            "role": "admin",
            "iat": int(time.time()), 
            "exp": int(time.time()) + (24 * 3600)
        },
        priv,
        algorithm="RS256"
    )

    test_html_path = Path("frontend/test.html")
    content = test_html_path.read_text(encoding="utf-8")
    
    import re
    # Update mockJWT
    content = re.sub(r'const mockJWT = ".*?";', f'const mockJWT = "{token}";', content)
    # Update WIDGET_ORIGIN
    content = re.sub(r'const WIDGET_ORIGIN = ".*?";', f'const WIDGET_ORIGIN = "http://localhost:3000";', content)
    # Update iframe src
    content = re.sub(r'src="http://localhost:5173"', 'src="http://localhost:3000"', content)
    
    test_html_path.write_text(content, encoding="utf-8")
    print(f"Successfully updated test.html with fresh token: {token[:20]}...")

    # Also update app.jsx for standalone dev widget UI
    app_jsx_path = Path("frontend/widget/src/app.jsx")
    if app_jsx_path.exists():
        app_content = app_jsx_path.read_text(encoding="utf-8")
        app_content = re.sub(r'const devToken = "(.*?)";', f'const devToken = "{token}";', app_content)
        app_jsx_path.write_text(app_content, encoding="utf-8")
        print("Successfully updated app.jsx with fresh token.")

if __name__ == "__main__":
    update()
