import re

src = open('src/api/review/review_routes.py').read()

# Strategy: For each function def, find the request line, move it to first param position.
# First replace the Depends hack with bare Request
src = src.replace('request: Request = Depends(lambda req: req),', 'request: Request,')
src = src.replace('request: Request = Depends(lambda req: req),', 'request: Request,')  # duplicate

# Now find each async function def and move request to first position
lines = src.split('\n')
i = 0
while i < len(lines):
    line = lines[i]
    # Check if this is a function definition
    if re.match(r'\s*async def \w+\(', line):
        func_name = re.search(r'def (\w+)\(', line).group(1)
        # Collect params until ):
        j = i + 1
        param_lines = []
        found_colon = False
        while j < len(lines):
            if lines[j].strip().startswith('):'):
                found_colon = True
                break
            param_lines.append(lines[j])
            j += 1
        
        if not found_colon:
            i += 1
            continue
        
        # Check if any param line contains 'request: Request,'
        request_idx = None
        for idx, pl in enumerate(param_lines):
            if 'request: Request,' in pl and '# P112' not in pl:
                request_idx = idx
                break
        
        if request_idx is not None:
            # Extract the request line
            req_line = param_lines[request_idx]
            # Check if it's NOT already first param
            if request_idx > 0:
                # Remove request from current position
                param_lines.pop(request_idx)
                # Find proper indentation
                first_param = param_lines[0]
                indent = re.match(r'^(\s*)', first_param).group(1)
                # Insert as first param
                # Format: indent + "request: Request,"
                param_lines.insert(0, indent + 'request: Request,')
            
            # Replace old param lines with new
            lines[i+1:j] = param_lines
        
        i = j  # skip past ):
    else:
        i += 1

src = '\n'.join(lines)

# Verify
try:
    compile(src, 'review_routes.py', 'exec')
    print('COMPILE OK')
except SyntaxError as e:
    print(f'SYNTAX ERROR at line {e.lineno}: {e.msg}')
    lines2 = src.split('\n')
    for k in range(max(0, e.lineno-5), min(len(lines2), e.lineno+3)):
        print(f'  {k+1}: {lines2[k]}')

open('src/api/review/review_routes.py', 'w').write(src)
print('Done')