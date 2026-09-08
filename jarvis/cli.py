import asyncio
from jarvis.orchestrator import Orchestrator

async def main():
    j=Orchestrator(); sid=None
    print("JARVIS v0.2 — type 'exit' to quit")
    while True:
        msg=input("You> ").strip()
        if msg.lower() in {"exit","quit"}: break
        r=await j.handle(msg,sid); sid=r["session_id"]
        print(f"JARVIS [{r['provider']}:{r['model']}]> {r['message']}\n")

if __name__=="__main__": asyncio.run(main())
