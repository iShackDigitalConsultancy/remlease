import requests
URL = "https://rem-leases-production.up.railway.app"
TEST_EMAIL = "phase3test@ishack.co.za"
TEST_PASSWORD = "Password123!"
res = requests.post(f"{URL}/api/auth/login", data={"username": TEST_EMAIL, "password": TEST_PASSWORD})
token = res.json().get("access_token")
headers = {"Authorization": f"Bearer {token}"}
ws_list = requests.get(f"{URL}/api/workspaces", headers=headers).json()
for w in ws_list:
    if w["documents"]:
        print(w["documents"][0]["id"])
        break
