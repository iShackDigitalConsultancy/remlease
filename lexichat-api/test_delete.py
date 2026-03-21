import requests
import time
import sys

# wait for server
for _ in range(10):
    try:
        r = requests.options("http://localhost:8080/api/workspaces")
        if r.status_code == 200: break
    except:
        time.sleep(1)

# create workspace
res = requests.post("http://localhost:8080/api/workspaces", data={"name": "test_del"}, headers={"X-Session-Id": "123_del"})
ws_id = res.json()["id"]
print("WS:", ws_id)

# upload file
with open("dummy.pdf", "rb") as f:
    res = requests.post(f"http://localhost:8080/api/upload/{ws_id}", files={"file": f}, headers={"X-Session-Id": "123_del"})
doc_id = res.json()["doc_id"]
print("UPLOAD RESP:", res.text)

# get workspaces
res = requests.get("http://localhost:8080/api/workspaces", headers={"X-Session-Id": "123_del"})
print("WORKSPACES:", res.json())

# delete document
res = requests.delete(f"http://localhost:8080/api/documents/{doc_id}", headers={"X-Session-Id": "123_del"})
print("DELETE STATUS:", res.status_code)
print("DELETE RESP:", res.text)
