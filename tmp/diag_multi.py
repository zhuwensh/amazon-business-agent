import asyncio, json, os, socket, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

env = dict(os.environ)
env["SLACK_WEBHOOK_URL"] = "https://hooks.slack.com/services/T00000000/B00000000/DIAGNOSTIC_INVALID"
env["MCP_HTTP"] = "1"
env["MCP_PORT"] = "8099"
env["SLACK_FINANCE_CHANNEL"] = "#finance"

logpath = os.path.join(os.environ.get("TEMP", ROOT), "bfa_diag_mcp.log")
log = open(logpath, "w")
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


print("diag MCP server up on 8099:", wait(8099))

from mcp_server.config import bootstrap

bootstrap()
from agent.agent import BusinessAgent

agent = BusinessAgent(mcp_url="http://127.0.0.1:8099/mcp")

turns = [
    "Which of our customers have overdue invoices? Check Acme and Globex.",
    "Chase both and send it to the channel.",
    "Yes, go ahead.",
]

for i, t in enumerate(turns, 1):
    print("=" * 62, flush=True)
    print("TURN", i, "| USER:", t, flush=True)
    try:
        r = asyncio.run(agent.ask(t, session_id="diag-multi"))
    except Exception as exc:
        print("TURN FAILED:", repr(exc)[:300], flush=True)
        break
    print("AGENT:", r.get("reply"), flush=True)
    for step in r.get("trace", []):
        print("   tool:", step.get("tool"), "| args:", json.dumps(step.get("arguments")), "| ok:", step.get("ok"), "| needs_confirmation:", step.get("needs_confirmation"), flush=True)
        if step.get("spoken"):
            print("        spoken:", step.get("spoken"), flush=True)

srv.terminate()
time.sleep(1)
print("=" * 62)
print("diag server log tail:")
print(open(logpath, errors="replace").read()[-500:])
