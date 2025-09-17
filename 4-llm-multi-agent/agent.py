"""
4 - Parallel Sub-Agent with Sequential parent-workflow
"""

import logging
import os
from google.adk.agents import Agent, SequentialAgent, ParallelAgent
from tools.tools import get_purchase_history, check_refund_eligibility, process_refund, send_email_tool
from tools.prompts import (
    top_level_prompt,
    purchase_history_subagent_prompt,
    check_eligibility_subagent_prompt_parallel,
    process_refund_subagent_prompt,
    root_agent_prompt,
    new_top_level_prompt
)

logger = logging.getLogger(__name__)

#GEMINI_MODEL = "gemini-2.5-flash-preview-05-20"
GEMINI_MODEL = os.getenv("MODEL")


email_agent = Agent(
    model=GEMINI_MODEL,
    name="EmailSenderAgent",
    description="Sends email using Gmail API",
    instruction="""
    You are an email assistant. Use the tool to send an email to the specified recipient.
    Make sure to include a subject and a message body. Confirm once the email is sent.If you don't have the receiepnt's email id, pls ask user to provide receiepnt's email id.
     
    """,
    tools=[send_email_tool],
    output_key="email_status"
)


purchase_verifier_agent = Agent(
    model=GEMINI_MODEL,
    name="PurchaseVerifierAgent",
    description="Verifies customer purchase history using the internal database",
    instruction=purchase_history_subagent_prompt,
    tools=[get_purchase_history],
    output_key="purchase_history",
)

refund_eligibility_agent = Agent(
    model=GEMINI_MODEL,
    name="RefundEligibilityAgent",
    description="Determines refund eligibility based on policies",
    instruction=check_eligibility_subagent_prompt_parallel,
    tools=[check_refund_eligibility],
    output_key="is_refund_eligible",
)

verifier_agent = ParallelAgent(
    name="VerifierAgent",
    description="Checks purchase history and refund eligibility in parallel",
    sub_agents=[purchase_verifier_agent, refund_eligibility_agent],
)

refund_processor_agent = Agent(
    model=GEMINI_MODEL,
    name="RefundProcessorAgent",
    description="Processes refunds or provides rejection explanations",
    instruction=new_top_level_prompt
    + "Specifically, your subagent has this task: "
    + process_refund_subagent_prompt,
    tools=[process_refund],
    output_key="refund_confirmation_message",
)

seq_agent = SequentialAgent(
    name="SequentialRefundProcessor",
    description="Processes customer refunds in a fixed sequential workflow",
    sub_agents=[
        verifier_agent,
        refund_processor_agent,
        email_agent
    ],
)

####################
root_agent = Agent(
    model=GEMINI_MODEL,
    name="RefundMultiAgent",
    description="Customer refund multi LLM agent for Crabby's Taffy company",
    instruction="""
    You are a multi agent system that coordinates sub-agents. Execute the following instructions in as few "turns" as you can, only prompting the user when needed. Coordinate the sub agents behind the scenes...
    """
    + root_agent_prompt,
    sub_agents=[seq_agent],
)
