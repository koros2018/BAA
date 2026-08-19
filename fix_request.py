import re

src = open('src/api/review/review_routes.py').read()

# Fix: replace all `request: Request = None` with `Depends(lambda req: req)`
# This makes `request` a proper FastAPI dependency that auto-injects the actual Request
old = 'request: Request = None'
new = 'request: Request = Depends(lambda req: req)'
count = src.count(old)
print(f'Replacing {count} occurrences')
src = src.replace(old, new)

assert old not in src, 'Still has request: Request = None'
print('All replaced')

try:
    compile(src, 'review_routes.py', 'exec')
    print('COMPILE OK')
except SyntaxError as e:
    print(f'SYNTAX ERROR: {e}')

open('src/api/review/review_routes.py', 'w').write(src)
print('Done')