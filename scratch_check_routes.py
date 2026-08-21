import re

with open('fleed_whitelist/static/app.js', 'r', encoding='utf-8') as f:
    js = f.read()

with open('fleed_whitelist/server.py', 'r', encoding='utf-8') as f:
    server = f.read()

# Extract apiCall endpoints from JS
# e.g., apiCall("/api/sessions", ...) or apiCall(`/api/scripts/${slug}/flags`, ...)
js_calls = set()
for match in re.findall(r'apiCall\([`"\'](/api/[^`"\'\?]+)', js):
    # normalize template literals like ${...} to {param}
    normalized = re.sub(r'\$\{[^\}]+\}', '{param}', match)
    js_calls.add(normalized)

# Extract FastAPI routes from server.py
# e.g. @app.get("/api/...") or @app.post("/api/...")
py_routes = set()
for match in re.findall(r'@app\.(?:get|post|patch|delete|put)\([`"\'](/api/[^`"\']+)', server):
    # normalize {slug} to {param}
    normalized = re.sub(r'\{[^\}]+\}', '{param}', match)
    py_routes.add(normalized)

print("JS API endpoints:", len(js_calls))
print("Python API routes:", len(py_routes))
print("\nJS calls missing in server.py:")
for call in sorted(js_calls):
    if call not in py_routes:
        print("  MISSING:", call)

print("\nPython routes not called by JS:")
for route in sorted(py_routes):
    if route not in js_calls:
        print("  UNUSED:", route)
