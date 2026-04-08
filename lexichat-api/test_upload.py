import requests
import time
import sys


if __name__ == "__main__":
    # wait for server
    for _ in range(30):
        try:
            r = requests.options("http://localhost:8080/api/workspaces")
            if r.status_code == 200: break
        except:
            time.sleep(1)

    # create workspace
    res = requests.post("http://localhost:8080/api/workspaces", data={"name": "test"}, headers={"X-Session-Id": "123"})
    if res.status_code != 200:
        print("Failed to create WS", res.text)
        sys.exit(1)
    ws_id = res.json()["id"]
    print("WS:", ws_id)

    # upload file
    try:
        with open("dummy.pdf", "rb") as f:
            res = requests.post(f"http://localhost:8080/api/upload/{ws_id}", files={"file": f}, headers={"X-Session-Id": "123"})
        print("STATUS:", res.status_code)
        print("RESP:", res.text)
    except Exception as e:
        print("CURL EXCEPTION:", e)
