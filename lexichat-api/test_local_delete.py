import requests
import sys
import time


if __name__ == "__main__":
    base = "http://localhost:8081/api"
    headers = {"X-Session-Id": "123_del_local"}

    # wait for server
    for _ in range(10):
        try:
            r = requests.options(f"{base}/workspaces")
            if r.status_code == 200: break
        except:
            time.sleep(1)

    try:
        print("Creating WS...")
        res = requests.post(f"{base}/workspaces", data={"name": "test_del"}, headers=headers)
        ws_id = res.json()["id"]

        print("Uploading to WS:", ws_id)
        with open("knowledge_base/za/BasicConditionsOfEmploymentAct.pdf", "rb") as f:
            res = requests.post(f"{base}/upload/{ws_id}", files={"file": f}, headers=headers)
        if "doc_id" not in res.json():
            print("Upload Failed:", res.text)
            sys.exit(1)
        
        doc_id = res.json()["doc_id"]
        print("Uploaded Doc ID:", doc_id)

        print("Deleting...")
        res = requests.delete(f"{base}/documents/{doc_id}", headers=headers)
        print("Del Status:", res.status_code)
        print("Del Body:", res.text)
    except Exception as e:
        print("Exception:", e)
