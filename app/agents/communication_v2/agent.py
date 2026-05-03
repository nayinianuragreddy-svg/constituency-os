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

import logging
import os
from typing import Optional

from sqlalchemy.engine import Engine

from app.agents.base import BaseAgent, AgentContext, AgentResult
from app.agents.runtime import LLMClient, PromptRenderer, StructuredDataValidator, SubstringGroundingChecker
from app.agents.communication_v2.tools import (
    SaveCitizenField,
    LoadCategorySchema,
    AddToHistory,
    ExtractStructuredData,
    ConfirmWithCitizen,
    CreateTicket,
    LookupTicketByNumber,
    EscalateToHuman,
)

logger = logging.getLogger(__name__)

PROMPT_PATH = os.path.join(
    os.path.dirname(__file__), "prompts", "system_v2_1.md"
)

# Tools whose successful execution warrants re-invoking the LLM so it can react
# to the updated state (e.g. schema just loaded, fields just persisted).
_STATE_CHANGING_TOOLS = {
    "load_category_schema", "extract_structured_data", "confirm_with_citizen",
    "create_ticket", "escalate_to_human",
}


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

        self._tools = {
            t.name: t
            for t in [
                SaveCitizenField(),
                LoadCategorySchema(),
                AddToHistory(),
                ExtractStructuredData(),
                ConfirmWithCitizen(),
                CreateTicket(),
                LookupTicketByNumber(),
                EscalateToHuman(),
            ]
        }

    def response_schema(self) -> dict:
        """The JSON schema the LLM must produce per turn.

        tool_calls is required (not optional) because OpenAI strict mode requires all
        declared properties to be in 'required'. The LLM returns [] when no tools are needed.

        arguments uses anyOf with one branch per tool. Each branch defines the exact allowed
        properties for one tool with additionalProperties=false.
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
                                    # extract_structured_data
                                    {
                                        "type": "object",
                                        "properties": {
                                            "subcategory_code": {"type": "string"},
                                            "source_text": {"type": "string"},
                                            "extracted_fields": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "field_name": {"type": "string"},
                                                        "value": {"type": "string"},
                                                    },
                                                    "required": ["field_name", "value"],
                                                    "additionalProperties": False,
                                                },
                                            },
                                        },
                                        "required": ["subcategory_code", "source_text", "extracted_fields"],
                                        "additionalProperties": False,
                                    },
                                    # confirm_with_citizen
                                    {
                                        "type": "object",
                                        "properties": {
                                            "language": {"type": "string"},
                                        },
                                        "required": ["language"],
                                        "additionalProperties": False,
                                    },
                                    # create_ticket
                                    {
                                        "type": "object",
                                        "properties": {
                                            "citizen_confirmation": {
                                                "type": "string",
                                                "enum": ["yes", "confirmed", "correct", "ok", "haan", "avunu"],
                                            },
                                        },
                                        "required": ["citizen_confirmation"],
                                        "additionalProperties": False,
                                    },
                                    # lookup_ticket_by_number
                                    {
                                        "type": "object",
                                        "properties": {
                                            "ticket_number": {"type": "string"},
                                            "caller": {
                                                "type": "string",
                                                "enum": ["communication", "dashboard", "master", "department"],
                                            },
                                        },
                                        "required": ["ticket_number", "caller"],
                                        "additionalProperties": False,
                                    },
                                    # escalate_to_human
                                    {
                                        "type": "object",
                                        "properties": {
                                            "reason_category": {
                                                "type": "string",
                                                "enum": ["safety_emergency", "suspicious_activity", "out_of_scope", "other"],
                                            },
                                            "reason_summary": {"type": "string"},
                                            "suggested_priority": {
                                                "type": "string",
                                                "enum": ["urgent", "normal"],
                                            },
                                        },
                                        "required": ["reason_category", "reason_summary", "suggested_priority"],
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
        """Multi-hop dispatch loop (up to max_hops per Doc C §3).

        Each hop:
        1. Re-reads state so the LLM sees the latest DB values.
        2. Renders the system prompt including any loaded schema.
        3. Calls the LLM.
        4. Executes all tool_calls from the response.
        5. Stops if no state-changing tool succeeded (reply is ready),
           otherwise hops again so the LLM can react.
        """
        total_cost = 0.0
        total_input_tokens = 0
        total_output_tokens = 0
        all_tool_calls_made: list[dict] = []
        final_reply_text: Optional[str] = None
        hops_used = 0
        extract_ever_ran = False  # track across all hops

        for hop in range(self.max_hops):
            hops_used = hop + 1

            # Re-read state on every hop so each LLM turn sees current DB values
            try:
                summary = self._state_reader.read(context.conversation_id)
            except Exception as exc:
                return self._fail("read_state_failed", context, str(exc),
                                  cost_usd=total_cost)

            category_schema = self._extract_schema_for_prompt(summary)

            try:
                system_prompt = self._prompt_renderer.render(
                    conversation_summary=summary,
                    category_schema=category_schema,
                    constituency_config=self._constituency_config,
                )
            except Exception as exc:
                return self._fail("render_failed", context, str(exc),
                                  cost_usd=total_cost)

            try:
                llm_response = self._llm_client.call(
                    model=self._model,
                    system_prompt=system_prompt,
                    user_message=context.incoming_message,
                    response_schema=self.response_schema(),
                    max_completion_tokens=8000,
                )
            except Exception as exc:
                return self._fail("llm_call_failed", context, str(exc),
                                  cost_usd=total_cost)

            total_cost += llm_response.cost_usd
            total_input_tokens += llm_response.input_tokens
            total_output_tokens += llm_response.output_tokens

            parsed = llm_response.parsed
            reply_text = parsed.get("reply_text") or ""
            if reply_text:
                final_reply_text = reply_text

            # Execute all tool calls and track what happened this hop
            schema_loaded_this_hop = False
            extract_ran = False
            all_required = False
            confirmed = False
            ticket_filed_this_hop = False
            ticket_number_filed: Optional[str] = None

            for call in parsed.get("tool_calls") or []:
                tool_result = self._execute_tool(call, context.conversation_id)
                all_tool_calls_made.append(tool_result)
                name = call.get("name")

                if tool_result.get("success"):
                    if name == "load_category_schema":
                        schema_loaded_this_hop = True
                    elif name == "extract_structured_data":
                        extract_ran = True
                        extract_ever_ran = True
                        if (tool_result.get("data") or {}).get("all_required_collected"):
                            all_required = True
                    elif name == "confirm_with_citizen":
                        readback = (tool_result.get("data") or {}).get("readback_text")
                        if readback:
                            final_reply_text = readback
                        confirmed = True
                    elif name == "create_ticket":
                        ticket_filed_this_hop = True
                        ticket_number_filed = (tool_result.get("data") or {}).get("ticket_number")

            # When all required fields are collected, auto-trigger confirm_with_citizen
            # if the LLM didn't call it in this hop. The readback is deterministic so we
            # don't need another LLM turn just to ask for confirmation.
            if all_required and not confirmed:
                auto_call = {"name": "confirm_with_citizen", "arguments": {"language": "english"}}
                auto_result = self._execute_tool(auto_call, context.conversation_id)
                all_tool_calls_made.append(auto_result)
                if auto_result.get("success"):
                    readback = (auto_result.get("data") or {}).get("readback_text")
                    if readback:
                        final_reply_text = readback
                    confirmed = True

            # If create_ticket succeeded this hop, ensure the ticket number appears in the reply.
            # The LLM composes reply_text before tool results are known, so we append the ticket
            # number here rather than re-hopping (which would cause duplicate ticket creation).
            if ticket_filed_this_hop and ticket_number_filed:
                if ticket_number_filed not in (final_reply_text or ""):
                    if final_reply_text:
                        final_reply_text = (
                            f"{final_reply_text.rstrip()} "
                            f"Your ticket number is {ticket_number_filed}. "
                            "Our team will review it shortly."
                        )
                    else:
                        final_reply_text = (
                            f"Your complaint has been registered. "
                            f"Ticket number: {ticket_number_filed}. "
                            "Our team will review it shortly."
                        )

            # Re-hop ONLY when load_category_schema just ran and the LLM hasn't yet had a
            # chance to extract fields with the newly visible schema. All other outcomes
            # (confirmed, extract ran with pending fields, or no schema change) mean the
            # current reply_text is ready to send.
            should_rehop = schema_loaded_this_hop and not extract_ran and not confirmed
            if not should_rehop:
                break

        # If we exhausted hops without a reply, log a warning
        if not final_reply_text:
            logger.warning(
                "dispatch exhausted %d hops without a reply_text (conversation_id=%s)",
                hops_used,
                context.conversation_id,
            )

        # Log to agent_actions
        try:
            self._action_logger.log(
                agent_name=self.agent_name,
                conversation_id=context.conversation_id,
                action_type="dispatch",
                payload={
                    "incoming_message": context.incoming_message,
                    "hops": hops_used,
                    "tool_calls": all_tool_calls_made,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                },
                cost_usd=total_cost,
                hops_used=hops_used,
                error=None,
            )
        except Exception:
            pass

        return AgentResult(
            reply_text=final_reply_text,
            tool_calls_made=all_tool_calls_made,
            cost_usd=total_cost,
            hops_used=hops_used,
            escalated=False,
            error=None,
        )

    def _execute_tool(self, call: dict, conversation_id: str) -> dict:
        """Execute a single tool call and return a structured result dict."""
        tool_name = call.get("name")
        tool_args = call.get("arguments") or {}
        tool = self._tools.get(tool_name)

        if tool is None:
            return {
                "name": tool_name,
                "args": tool_args,
                "success": False,
                "error": f"unknown tool: {tool_name}",
            }

        try:
            result = tool.execute(tool_args, self._engine, conversation_id)
        except Exception as exc:
            return {
                "name": tool_name,
                "args": tool_args,
                "success": False,
                "error": f"tool raised: {exc!r}",
            }

        return {
            "name": tool_name,
            "args": tool_args,
            "success": result.success,
            "data": result.data,
            "error": result.error,
        }

    def _extract_schema_for_prompt(self, summary: dict) -> Optional[dict]:
        """If a category schema is loaded in state, fetch it for the PromptRenderer.

        Returns a dict in the shape PromptRenderer._format_schema expects:
        {"subcategory_code": str, "fields": [...]}
        or None if no schema is loaded.
        """
        current_complaint = summary.get("current_complaint") or {}
        if not current_complaint.get("category_schema_loaded"):
            return None

        subcategory_code = current_complaint.get("subcategory_code")
        if not subcategory_code:
            return None

        try:
            import sqlalchemy as sa
            with self._engine.connect() as conn:
                row = conn.execute(
                    sa.text(
                        "SELECT required_fields, display_name_en"
                        " FROM complaint_subcategories WHERE code = :code"
                    ),
                    {"code": subcategory_code},
                ).fetchone()
            if row is None:
                return None
            fields = row[0]
            if isinstance(fields, str):
                import json
                fields = json.loads(fields)
            return {"subcategory_code": subcategory_code, "fields": fields or []}
        except Exception:
            return None
