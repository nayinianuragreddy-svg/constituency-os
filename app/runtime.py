from app.agents.communication import CommunicationAgent
from app.agents.dashboard import DashboardAgent
from app.agents.master import MasterAgent
from app.contracts import AgentMessage, RuntimeRequest, RuntimeResponse


class RuntimeOrchestrator:
    """Runtime-first orchestration layer built from stateless agents."""

    def __init__(self) -> None:
        self.communication_agent = CommunicationAgent(name="CommunicationAgent")
        self.dashboard_agent = DashboardAgent(name="DashboardAgent")
        self.master_agent = MasterAgent(name="MasterAgent")

    def dispatch(self, request: RuntimeRequest) -> RuntimeResponse:
        base_message = AgentMessage(
            sender="Runtime",
            receiver="Constituency",
            body=f"{request.action}:{request.payload}",
        )
        communication_msg = self.communication_agent.process(base_message)
        dashboard_msg = self.dashboard_agent.process(communication_msg)
        master_msg = self.master_agent.process(dashboard_msg)
        return RuntimeResponse(
            status="ok",
            communication=communication_msg,
            dashboard=dashboard_msg,
            master=master_msg,
        )
