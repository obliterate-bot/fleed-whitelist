import re

with open('fleed_whitelist/static/app.js', 'r', encoding='utf-8') as f:
    js = f.read()

with open('fleed_whitelist/server.py', 'r', encoding='utf-8') as f:
    server = f.read()

calls = set(re.findall(r'apiCall\([`"\'](/api/[^`"\'\?]+)', js))
routes = set(re.findall(r'@app\.(?:get|post|patch|delete|put)\([`"\'](/api/[^`"\']+)', server))

def norm(path):
    # replace ${...} or {slug} with {param}
    p = re.sub(r'\$\{[^\}]+\}', '{param}', path)
    p = re.sub(r'\{[^\}]+\}', '{param}', p)
    return p

norm_routes = {norm(r) for r in routes}

print("=== ALL apiCalls in JS that are NOT registered in server.py ===")
for c in sorted(calls):
    nc = norm(c)
    if nc not in norm_routes:
        print(f"  MISSING IN SERVER: {c} (normalized: {nc})")
