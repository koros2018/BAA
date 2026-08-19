import json, sqlite3, subprocess, time

# Step 1: Login as boss_ke
r = subprocess.run([
    "curl", "-s", "-X", "POST", "http://localhost:8000/collab/auth/login",
    "-H", "Content-Type: application/json",
    "-d", '{"username":"boss_ke","password":"test123"}'
], capture_output=True, text=True)
login = json.loads(r.stdout)
assert login["status"] == "success", f"Login failed: {login}"
TOKEN = login["token"]
print(f"Step 1: Login OK, token={TOKEN[:12]}...")

# Step 2: Create team
r = subprocess.run([
    "curl", "-s", "-X", "POST", "http://localhost:8000/collab/teams",
    "-H", "Content-Type: application/json",
    "-H", f"Authorization: Bearer {TOKEN}",
    "-d", '{"name":"E2E Team","description":"Full flow test"}'
], capture_output=True, text=True)
team_resp = json.loads(r.stdout)
assert team_resp["status"] == "success"
TEAM_ID = team_resp["team"]["id"]
print(f"Step 2: Team created, TEAM_ID={TEAM_ID}")

# Step 3: Create project
r = subprocess.run([
    "curl", "-s", "-X", "POST", "http://localhost:8000/collab/projects",
    "-H", "Content-Type: application/json",
    "-H", f"Authorization: Bearer {TOKEN}",
    "-d", json.dumps({"name": "E2E Project", "team_id": TEAM_ID, "description": "End-to-end", "building_type": "civil"})
], capture_output=True, text=True)
proj_resp = json.loads(r.stdout)
assert proj_resp["status"] == "success"
PROJ_ID = proj_resp["project"]["id"]
print(f"Step 3: Project created, PROJ_ID={PROJ_ID}")

# Step 4: Review with headers
API_KEY = "***"
DXF = "data/drawings/real/2.1电气170825-报审.dxf"
r = subprocess.run([
    "curl", "-s", "-X", "POST", "http://localhost:8000/review?building_type=civil&standard=GB+50016-2014",
    "-F", f"file=@{DXF}",
    "-H", f"Authorization: Bearer {API_KEY}",
    "-H", f"X-Team-Id: {TEAM_ID}",
    "-H", f"X-Project-Id: {PROJ_ID}",
    "--max-time", "60"
], capture_output=True, text=True)
review = json.loads(r.stdout)
assert review["status"] == "success"
FILE_ID = review["file_id"]
print(f"Step 4: Review OK, FILE_ID={FILE_ID}")

# Step 5: Verify DB has team_id/project_id
time.sleep(1)
conn = sqlite3.connect("data/review_history.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()
row = cur.execute("SELECT team_id, project_id FROM review_history WHERE id=?", (FILE_ID,)).fetchone()
if row:
    db_team = row["team_id"]
    db_proj = row["project_id"]
    print(f"Step 5: DB record: team_id='{db_team}', project_id='{db_proj}'")
    if db_team == TEAM_ID and db_proj == PROJ_ID:
        print("PASS: team_id and project_id correctly persisted!")
    else:
        print(f"FAIL: expected team={TEAM_ID} proj={PROJ_ID}, got team={db_team} proj={db_proj}")
else:
    print("FAIL: No DB record found")
conn.close()

# Step 6: Verify /review/history API returns team_id/project_id
r = subprocess.run([
    "curl", "-s", "http://localhost:8000/review/history?limit=5",
    "-H", f"Authorization: Bearer {API_KEY}"
], capture_output=True, text=True)
hist = json.loads(r.stdout)
items = hist.get("items", [])
for item in items:
    if item["id"] == FILE_ID:
        print(f"Step 6: API history: teamId='{item.get('teamId','')}', projectId='{item.get('projectId','')}'")
        break
else:
    print("Step 6: No matching history item found")