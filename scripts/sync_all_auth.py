# scripts/sync_all_auth.py
import jwt
import time
import os
import re
from pathlib import Path

def sync():
    # 1. Regenerate Keys on Host
    os.system("python scripts/generate_jwt_keys.py")
    
    priv_path = Path(".keys/private_key.pem")
    priv = priv_path.read_text()
    
    # 2. Create FRESH Token
    token = jwt.encode(
        {"sub": "test_user_123", "iat": int(time.time()), "exp": int(time.time()) + 3600},
        priv,
        algorithm="RS256"
    )
    
    # 3. Update test.html
    html_p = Path("frontend/test.html")
    content = html_p.read_text(encoding="utf-8")
    content = re.sub(r'const mockJWT = ".*?";', f'const mockJWT = "{token}";', content)
    html_p.write_text(content, encoding="utf-8")
    
    # 4. Update app.jsx
    jsx_p = Path("frontend/widget/src/app.jsx")
    content = jsx_p.read_text(encoding="utf-8")
    content = re.sub(r'const devToken = ".*?";', f'const devToken = "{token}";', content)
    jsx_p.write_text(content, encoding="utf-8")
    
    print(f"✅ Sync Complete!")
    print(f"🔑 Keys regenerated and token updated in test.html and app.jsx.")

if __name__ == "__main__":
    sync()
