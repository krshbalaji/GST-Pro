"""Container health probe for FastAPI."""
import urllib.request

urllib.request.urlopen("http://127.0.0.1:8000/ready", timeout=3).read()
