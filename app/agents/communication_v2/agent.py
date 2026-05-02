"""CommunicationAgent: the V2.0 agent that talks to citizens.

Subclasses BaseAgent. Composes the three runtime components plus the tool registry.

Doc C v2.1 §3 spec:
- agent_name: 'communication'
- runtime_pattern: 'reactive'
- max_hops: 3
- max_session_turns: 40
- cost_ceiling_usd_per_day: 2.00
- model: from env LLM_MODEL_COMMUNICATION (default gpt-4o-mini)
"""

from __future__ import annotations

import os
from typing import Optional

from sqlalchemy.engine import Engine

from app.agents.base import BaseAgent, AgentContext, AgentResult
from app.agents.runtime import (
    LLMClient,
    PromptRenderer,
    StructuredDataValidator,
    SubstringGroundingChecker,
)
from app.agents.communication_v2.tools import (
    SaveCitizenField,
    LoadCategorySchema,
    AddToHistory,
)


PROMPT_PATH = os.path.join(
    os.path.dirname(__file__), "prompts", "system_v2_1.md"
)


class CommunicationAgent(BaseAgent):
    agent_name = "communication"
    runtime_pattern = "reactive"
    max_hops = 3
    max_session_turns = 40
    cost_ceiling_usd_per_day = 2.00

    def __init__(
        self,
        engine: Engine,
        llm_client: Optional[LLMClient] = None,
        constituency_config: Optional[dict] = None,
        model: Optional[str] = None,
    ) -> None:
        llm_client = llm_client or LLMClient()
        prompt_renderer = PromptRenderer(
            agent_name=self.agent_name,
            prompt_template_path=PROMPT_PATH,
        )

        super().__init__(
            engine=engine,
            llm_client=llm_client,
            prompt_renderer=prompt_renderer,
            validator=StructuredDataValidator(),
            grounding_checker=SubstringGroundingChecker(),
            model=model or os.getenv("LLM_MODEL_COMMUNICATION"),
        )

        self._constituency_config = constituency_config or {
            "mla_name": "the MLA",
            "name": "this constituency",
        }

        # Tool registry — three tools for PR 5a; PR 5b and 5c add the rest.
        self._tools = {
            t.name: t
            for t in [
                SaveCitizenField(),
                LoadCategorySchema(),
                AddToHistory(),
            ]
        }

    def response_schema(self) -> dict:
        """The JSON schema the LLM must produce per turn.

        tool_calls is required (not optional) because OpenAI strict mode requires all
        declared properties to be in 'required'. The LLM returns [] when no tools are needed.

        arguments uses anyOf with one branch per tool. This is the strict-mode-compatible
        way to have a free-form arguments object: each branch defines the exact allowed
        properties for one tool with additionalProperties=false. The LLM picks the branch
        that matches the tool being called.
        """
        return {
            "type": "object",
            "properties": {
                "reply_text": {"type": "string"},
                "tool_calls": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "arguments": {
                                "anyOf": [
                                    # save_citizen_field
                                    {
                                        "type": "object",
                                        "properties": {
                                            "field_name": {"type": "string"},
                                            "value": {"type": "string"},
                                        },
                                        "required": ["field_name", "value"],
                                        "additionalProperties": False,
                                    },
                                    # load_category_schema
                                    {
                                        "type": "object",
                                        "properties": {
                                            "subcategory_code": {"type": "string"},
                                        },
                                        "required": ["subcategory_code"],
                                        "additionalProperties": False,
                                    },
                                    # add_to_history
                                    {
                                        "type": "object",
                                        "properties": {
                                            "role": {"type": "string"},
                                            "text": {"type": "string"},
                                        },
                                        "required": ["role", "text"],
                                        "additionalProperties": False,
                                    },
                                ]
                            },
                        },
                        "required": ["name", "arguments"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["reply_text", "tool_calls"],
            "additionalProperties": False,
        }

    def dispatch(self, context: AgentContext) -> AgentResult:
        """Override BaseAgent.dispatch to add tool execution after the LLM call.

        Flow:
        1. Read state from DB.
        2. Render system prompt.
        3. Call LLM with structured output.
        4. Execute any tool_calls returned by the LLM.
        5. Log the dispatch to agent_actions.
        6. Return AgentResult.
        """
        try:
            summary = self._state_reader.read(context.conversation_id)
        except Exception as exc:
            return self._fail("read_state_failed", context, str(exc))

        try:
            system_prompt = self._prompt_renderer.render(
                conversation_summary=summary,
                category_schema=None,
                constituency_config=self._constituency_config,
            )
        except Exception as exc:
            return self._fail("render_failed", context, str(exc))

        try:
            llm_response = self._llm_client.call(
                model=self._model,
                system_prompt=system_prompt,
                user_message=context.incoming_message,
                response_schema=self.response_schema(),
                max_completion_tokens=8000,
            )
        except Exception as exc:
            return self._fail("llm_call_failed", context, str(exc))

        parsed = llm_response.parsed

        # Execute tool calls
        tool_calls_made = []
        for call in parsed.get("tool_calls") or []:
            tool_name = call.get("name")
            tool_args = call.get("arguments") or {}
            tool = self._tools.get(tool_name)

            if tool is None:
                tool_calls_made.append({
                    "name": tool_name,
                    "args": tool_args,
                    "success": False,
                    "error": f"unknown tool: {tool_name}",
                })
                continue

            try:
                result = tool.execute(tool_args, self._engine, context.conversation_id)
            except Exception as exc:
                tool_calls_made.append({
                    "name": tool_name,
                    "args": tool_args,
                    "success": False,
                    "error": f"tool raised: {exc!r}",
                })
                continue

            tool_calls_made.append({
                "name": tool_name,
                "args": tool_args,
                "success": result.success,
                "data": result.data,
                "error": result.error,
            })

        # Log to agent_actions
        try:
            self._action_logger.log(
                agent_name=self.agent_name,
                conversation_id=context.conversation_id,
                action_type="dispatch",
                payload={
                    "incoming_message": context.incoming_message,
                    "parsed": parsed,
                    "model": llm_response.model,
                    "input_tokens": llm_response.input_tokens,
                    "output_tokens": llm_response.output_tokens,
                    "tool_calls": tool_calls_made,
                },
                cost_usd=llm_response.cost_usd,
                hops_used=1,
                error=None,
            )
        except Exception:
            pass

        return AgentResult(
            reply_text=parsed.get("reply_text"),
            tool_calls_made=tool_calls_made,
            cost_usd=llm_response.cost_usd,
            hops_used=1,
            escalated=False,
            error=None,
        )
