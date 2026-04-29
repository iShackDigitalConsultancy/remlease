import urllib.request, json, ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
api_base = 'https://rem-leases-production.up.railway.app/api'
headers = {'Authorization': 'Bearer ' + open('.token').read().strip() if False else '', 'Content-Type': 'application/json', 'Accept': 'text/event-stream'}
