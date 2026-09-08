from jarvis.agents.base import Agent
from jarvis.agents.research import ResearchAgent
from jarvis.agents.coding import CodingAgent
from jarvis.agents.data import DataAgent
from jarvis.agents.creative import CreativeAgent
from jarvis.agents.operations import OperationsAgent

class AgentManager:
    def __init__(self, router, tools):
        general=Agent(router,tools)
        self.agents={
            "general":general,
            "research":ResearchAgent(router,tools),
            "coding":CodingAgent(router,tools),
            "data":DataAgent(router,tools),
            "creative":CreativeAgent(router,tools),
            "operations":OperationsAgent(router,tools),
        }
    def get(self,name: str): return self.agents.get(name,self.agents["general"])
