"""Network diagnostic endpoint with command injection via os.system."""
import os
from fastapi import FastAPI

app = FastAPI()


@app.get("/api/network/ping")
def ping_host(host: str):
    """Ping a host and return the result."""
    exit_code = os.system(f"ping -c 3 {host}")
    return {
        "host": host,
        "reachable": exit_code == 0,
        "exit_code": exit_code,
    }


@app.get("/api/network/dns")
def dns_lookup(domain: str):
    """Look up DNS records for a domain."""
    result = os.popen(f"nslookup {domain}").read()
    return {"domain": domain, "result": result}
