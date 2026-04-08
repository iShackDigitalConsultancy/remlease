import requests
import sys


if __name__ == "__main__":
    base = "https://rem-leases-production.up.railway.app/api"
    headers = {"X-Session-Id": "123_del_prod"}

    try:
        print("Creating WS...")
        res = requests.post(f"{base}/workspaces", data={"name": "test_del"}, headers=headers)
        ws_id = res.json()["id"]

        print("Uploading to WS:", ws_id)
        with open("dummy.pdf", "rb") as f:
            res = requests.post(f"{base}/upload/{ws_id}", files={"file": f}, headers=headers)
        doc_id = res.json()["doc_id"]
        print("Doc ID:", doc_id)

        print("Deleting...")
        res = requests.delete(f"{base}/documents/{doc_id}", headers=headers)
        print("Del Status:", res.status_code)
        print("Del Body:", res.text)
    except Exception as e:
        print("Exception:", e)
