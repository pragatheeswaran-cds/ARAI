"""The vm profile with the development login (AM-74), end to end over HTTP, as the demonstration VM runs it.

Starts `arai serve` on port 8010 twice against DATABASE_URL (the environment, else the DATABASE_URL line of .env): once
without AUTH_DEV_ON_VM, which must be refused (the AM-70 guard stands), and once with it. Then, like a visitor behind the
VM's nginx: health open without any login (no shared login, AM-75), the personas, a sign-in as Priya (viewer), her refusals
(CSRF, reviewer, admin), the admin view as Admin, and the single sign-on route being off. Writes
reports/ui/<date>/vm-devlogin-result.json.

    uv run --no-sync python tests\\e2e\\vm_devlogin_check.py        # "13 of 13 checks passed"
"""
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
PORT = 8010
API = f"http://127.0.0.1:{PORT}/api/v1"
OUT = ROOT / "reports" / "ui" / datetime.now(tz=UTC).date().isoformat()


def database_url() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip()
    sys.exit("DATABASE_URL is not set and .env has no DATABASE_URL line")


BASE_ENV = {**os.environ, "DATABASE_URL": database_url(), "APP_PROFILE": "vm", "AUTH_MODE": "dev", "UI_ORIGINS": f"http://127.0.0.1:{PORT}"}
BASIC: dict = {}                      # no shared login in front of the API since AM-75; kept as the (empty) common header set
results = []


def check(name, ok, observed):
    results.append({"check": name, "pass": bool(ok), "observed": observed})
    print(f"{'PASS' if ok else 'FAIL'}  {name:50s} {observed}")


def serve(extra):
    return subprocess.Popen([sys.executable, "-m", "arai.cli", "serve", "--port", str(PORT)], cwd=ROOT, env={**BASE_ENV, **extra},
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def guard_stands():
    p = serve({})
    out = ""
    for _ in range(60):
        if p.poll() is not None:
            out = p.stdout.read()
            break
        time.sleep(1)
    else:
        p.kill()
        out = "still running after 60 s"
    line = next((ln.strip() for ln in out.splitlines() if "refused with APP_PROFILE=vm" in ln), out[-120:])
    check("guard: AUTH_MODE=dev refused on vm without the opt-in", p.returncode not in (None, 0) and "refused with APP_PROFILE=vm" in line,
          f"exit {p.returncode}; {line[:90]}")


def visitor_walk(c: httpx.Client):
    r = c.get(f"{API}/health")
    check("no shared login: health is open, 200", r.status_code == 200, f"{r.status_code} alive={r.json().get('alive')}")
    r = c.get(f"{API}/auth/dev-users", headers=BASIC)
    names = {u["display_name"]: u["roles"] for u in r.json().get("users", [])} if r.status_code == 200 else {}
    check("dev-users lists the personas", r.status_code == 200 and names.get("Admin") == ["admin"] and names.get("Priya") == ["viewer"],
          f"{r.status_code} {sorted(names)}")

    r = c.post(f"{API}/auth/dev-login", headers=BASIC, json={"user": "Priya"})
    set_cookie = r.headers.get("set-cookie", "")
    cookie = set_cookie.split(";")[0]
    flags = [f.strip() for f in set_cookie.split(";")[1:]]
    check("dev-login as Priya sets a Secure HttpOnly cookie", r.status_code == 200 and "Secure" in flags and "HttpOnly" in flags, f"{r.status_code} {flags}")
    as_priya = {**BASIC, "Cookie": cookie}
    me = c.get(f"{API}/me", headers=as_priya)
    body = me.json()
    check("/me: Priya is a viewer on auth_mode dev", me.status_code == 200 and body.get("roles") == ["viewer"] and body.get("auth_mode") == "dev",
          f"{me.status_code} roles={body.get('roles')} mode={body.get('auth_mode')}")
    csrf = body.get("csrf_token", "")
    r = c.get(f"{API}/runs/r/customers/c/reviews", headers=as_priya)
    check("viewer may read a review route (404: no such run)", r.status_code == 404, f"{r.status_code} {r.json().get('message', '')[:60]}")
    r = c.get(f"{API}/admin/users", headers=as_priya)
    check("viewer refused an admin route", r.status_code == 403 and "admin" in r.text, f"{r.status_code} {r.json().get('message', '')[:60]}")
    r = c.post(f"{API}/runs/r/customers/c/reviews", headers=as_priya, json={})
    check("POST without the CSRF header is refused", r.status_code == 403 and "csrf" in r.text.lower(), f"{r.status_code} {r.json().get('message', '')[:60]}")
    r = c.post(f"{API}/runs/r/customers/c/reviews", headers={**as_priya, "X-CSRF-Token": csrf}, json={})
    check("POST with CSRF, still refused for the role", r.status_code == 403 and "reviewer" in r.text, f"{r.status_code} {r.json().get('message', '')[:60]}")

    r = c.post(f"{API}/auth/dev-login", headers=BASIC, json={"user": "Admin"})
    as_admin = {**BASIC, "Cookie": r.headers.get("set-cookie", "").split(";")[0]}
    r = c.get(f"{API}/admin/users", headers=as_admin)
    check("Admin sees the people page", r.status_code == 200, f"{r.status_code} {str(r.json())[:70]}")
    r = c.get(f"{API}/admin/auth-events", headers=as_admin)
    check("sign-in log holds Priya's refusals", r.status_code == 200 and "refused" in r.text, f"{r.status_code} refused present={'refused' in r.text}")
    r = c.post(f"{API}/auth/dev-login", headers=BASIC, json={"user": "Mallory"})
    check("unknown persona is refused", r.status_code == 422, str(r.status_code))
    r = c.get(f"{API}/auth/login", headers=BASIC)
    check("the single sign-on route is off", r.status_code == 404, str(r.status_code))


def main() -> int:
    guard_stands()
    p = serve({"AUTH_DEV_ON_VM": "1"})
    c = httpx.Client(timeout=10)
    for _ in range(90):
        try:
            if c.get(f"{API}/health", headers=BASIC).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        if p.poll() is not None:
            print(p.stdout.read())
            sys.exit("the server exited during start-up")
        time.sleep(1)
    try:
        visitor_walk(c)
    finally:
        p.terminate()
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()
    passed = sum(r["pass"] for r in results)
    print(f"\n{passed} of {len(results)} checks passed")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "vm-devlogin-result.json").write_text(json.dumps({"checks": results, "passed": passed, "total": len(results)}, indent=1), encoding="utf-8")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
