"""Quick test: verify login-first flow and guest button."""
import requests

BASE = "http://127.0.0.1:5000"

# 1. Visit / without session -> should redirect to login
s = requests.Session()
r = s.get(BASE + "/", allow_redirects=False)
print(f"[1] GET /  -> Status {r.status_code}, Location: {r.headers.get('Location', '(none)')}")
assert r.status_code == 302, "Expected redirect"
assert "/auth/login" in r.headers["Location"], "Should redirect to login"

# 2. Follow the redirect -> should see login page
r2 = s.get(BASE + r.headers["Location"])
print(f"[2] GET /auth/login -> Status {r2.status_code}")
assert r2.status_code == 200
assert "Continue as Guest" in r2.text, "Guest button must be present"
assert "/guest" in r2.text, "Guest button must link to /guest"
print("    -> Login page has 'Continue as Guest' button pointing to /guest")

# 3. Click guest button (/guest) -> should set session, redirect to /
r3 = s.get(BASE + "/guest", allow_redirects=False)
print(f"[3] GET /guest -> Status {r3.status_code}, Location: {r3.headers.get('Location', '(none)')}")
assert r3.status_code == 302

# 4. Follow redirect -> should now show the main page
r4 = s.get(BASE + "/", allow_redirects=False)
print(f"[4] GET / (after guest) -> Status {r4.status_code}")
assert r4.status_code == 200, "Should show main page for guest"
assert "Generate Subtitles" in r4.text or "upload" in r4.text.lower()
print("    -> Main page loaded successfully as guest!")

# 5. Logout -> clears guest, redirects to login
r5 = s.get(BASE + "/auth/logout", allow_redirects=False)
print(f"[5] GET /auth/logout -> Status {r5.status_code}, Location: {r5.headers.get('Location', '(none)')}")

# 6. After logout, / should redirect to login again
r6 = s.get(BASE + "/", allow_redirects=False)
print(f"[6] GET / (after logout) -> Status {r6.status_code}, Location: {r6.headers.get('Location', '(none)')}")
assert r6.status_code == 302
assert "/auth/login" in r6.headers["Location"]

print("\n=== ALL TESTS PASSED ===")
