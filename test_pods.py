import urllib.request
import urllib.error

codes = []
for _ in range(10):
    try:
        codes.append(urllib.request.urlopen('http://localhost:8000/').getcode())
    except urllib.error.HTTPError as e:
        codes.append(e.code)
    except Exception as e:
        codes.append(str(e))
        
print("HTTP Codes:", codes)
