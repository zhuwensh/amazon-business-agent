
import os, re, pathlib, socket, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
os.chdir(ROOT)

KEY = re.search(r"experimental_bearer_token\s*=\s*\"([^\"]+)\"", pathlib.Path(os.path.expanduser("~/.codex/config.toml")).read_text(encoding="utf-8")).group(1)

env = dict(os.environ)
env["SLACK_WEBHOOK_URL"] = "https://hooks.slack.com/services/T00000000/B00000000/DIAGNOSTIC_INVALID"
env["MCP_HTTP"] = "1"
env["MCP_PORT"] = "8099"

log = open(os.path.join(os.environ.get("TEMP", str(ROOT)), "bfa_ds_mcp.log"), "w")
srv = subprocess.Popen([sys.executable, "-m", "mcp_server.server"], env=env, stdout=log, stderr=subprocess.STDOUT)


def wait(port, seconds=60):
    end = time.time() + seconds
    while time.time() < end:
        s = socket.socket()
        s.settimeout(0.5)
        ok = s.connect_ex(("127.0.0.1", port)) == 0
        s.close()
        if ok:
            return True
        time.sleep(0.5)
    return False


print("server up:", wait(8099), flush=True)

for model in ["deepseek-flash", "deepseek-v4-pro"]:
    renv = dict(os.environ)
    renv.update({"LLM_PROVIDER": "openai", "LLM_API_KEY": KEY, "LLM_BASE_URL": "https://api.deepseek.com", "LLM_MODEL": model})
    t0 = time.time()
    r = subprocess.run(
        [sys.executable, "-m", "agent.agent", "--mcp-url", "http://127.0.0.1:8099/mcp", "Does Acme have anything overdue?"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=renv, timeout=300,
    )
    print("=" * 58, flush=True)
    print("MODEL:", model, "| exit", r.returncode, "| {:.1f}s".format(time.time() - t0), flush=True)
    print((r.stdout or r.stderr)[-800:].encode("ascii", "replace").decode("ascii"), flush=True)

out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
for line in out.splitlines():
    parts = line.split()
    if len(parts) >= 5 and parts[0] == "TCP" and parts[1].endswith(":8099") and parts[3] == "LISTENING":
        subprocess.run(["taskkill", "/F", "/T", "/PID", parts[4]], capture_output=True)
print("diagnostic server stopped")
