"""
4 - Parallel Sub-Agent with Sequential parent-workflow
"""
import logging
import os
import sys
import re  # <-- added
from google.adk.agents import Agent, SequentialAgent, ParallelAgent
import asyncio
import gradio as gr
from google.adk import Agent as _ADKAgent  # avoid shadowing
from google.adk.runners import InMemoryRunner
from google.adk.sessions import Session
from google.genai import types
from dotenv import load_dotenv
# import google.cloud.logging
# from callback_logging import log_query_to_model, log_model_response
sys.path.append(".")
from tools.tools import get_purchase_history, check_refund_eligibility, process_refund, send_email_tool
from tools.prompts import (
    top_level_prompt,
    purchase_history_subagent_prompt,
    check_eligibility_subagent_prompt_parallel,
    process_refund_subagent_prompt,
    root_agent_prompt
)

# Environment setup
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
os.environ["GOOGLE_CLOUD_PROJECT"] = "qwiklabs-gcp-01-4487d8ebc8a0"
os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"
os.environ["MODEL"] = "gemini-2.5-flash"

logger = logging.getLogger(__name__)
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
    instruction=top_level_prompt
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

###############################################
app_name = "my_agent_app"
user_id = "user1"

# Create runner and session globally
runner = InMemoryRunner(agent=root_agent, app_name=app_name)
session = asyncio.run(runner.session_service.create_session(app_name=app_name, user_id=user_id))

# Async function to run agent
async def run_agent_query(user_input: str) -> str:
    content = types.Content(role="user", parts=[types.Part.from_text(text=user_input)])
    response_text = ""
    async for event in runner.run_async(user_id=user_id, session_id=session.id, new_message=content):
        if event.content.parts and event.content.parts[0].text:
            response_text += event.content.parts[0].text + "\n"
    return response_text.strip()

# Wrapper for Gradio to run async code
def gradio_agent_interface(user_input):
    return asyncio.run(run_agent_query(user_input))

# =========================
# Build Gradio UI (LIGHT THEME)
# =========================

# Light, clean default theme
theme = gr.themes.Default(
    primary_hue="blue",
    secondary_hue="green",
    neutral_hue="gray",
)

# --- NEW: sanitize assistant text coming back from the agent (UI-only) ---
def sanitize_response(text: str) -> str:
    """
    Remove a leading boolean echo like: true / false / "true" / 'false' (optional colon/dash),
    followed by whitespace/newline, without touching the rest of the content.
    """
    if not isinstance(text, str):
        return text
    # Case 1: boolean + newline(s)
    text = re.sub(
        r'^\s*["\']?(?:true|false)["\']?\s*[:\-]*\s*(?:\r?\n)+',
        '',
        text,
        flags=re.IGNORECASE
    )
    # Case 2 (fallback): boolean + space on same line
    text = re.sub(
        r'^\s*["\']?(?:true|false)["\']?\s*[:\-]*\s+',
        '',
        text,
        flags=re.IGNORECASE
    )
    return text

# Core chat function (UI-only; does not touch your agent code)
def chat(user_message, messages):
    # messages is a list[dict] with keys {"role","content"} because Chatbot uses type='messages'
    if not user_message or not user_message.strip():
        return messages, gr.update(value="")
    response = asyncio.run(run_agent_query(user_message))
    response = sanitize_response(response)  # <-- strip leading boolean echo
    new_messages = (messages or []) + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": response},
    ]
    return new_messages, gr.update(value="")

def clear_chat():
    return [], []

def show_working():
    # Show loading spinner and disable the Send button
    return (
        gr.update(visible=True),  # loading
        gr.update(interactive=False)  # send button
    )

def hide_working():
    return (
        gr.update(visible=False),  # loading
        gr.update(interactive=True)  # send button
    )

with gr.Blocks(theme=theme, css="""
/* ---------- Light App Surface ---------- */
.gradio-container {
  background: #f5f7fb; /* light neutral */
  color: #111827; /* gray-900 */
}
/* Header card */
.header-card {
  border: 1px solid #e5e7eb; /* gray-200 */
  background: linear-gradient(180deg, #ffffff, #fafafa);
  border-radius: 16px;
  padding: 18px 20px;
}
/* Chatbot surface */
.gr-chatbot {
  border: 1px solid #e5e7eb;
  background: #ffffff;
  border-radius: 14px !important;
}
/* Inputs */
textarea, input, .gr-textbox {
  background: #ffffff !important;
  border: 1px solid #e5e7eb !important;
  color: #111827 !important;
}
/* Buttons inherit theme; no dark overrides */
/* Spinner */
.loader {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: #4b5563; /* gray-600 */
  font-size: 0.95rem;
}
.loader:before {
  content: "";
  width: 14px;
  height: 14px;
  border: 2px solid rgba(59,130,246,0.35); /* blue-500 at 35% */
  border-top-color: #3b82f6; /* blue-500 */
  border-radius: 50%;
  display: inline-block;
  animation: spin .9s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg) } }
/* Right panel */
.side-card {
  border: 1px solid #e5e7eb;
  background: #ffffff;
  border-radius: 12px;
  padding: 12px;
}
""") as demo:
    # Create state INSIDE Blocks (prevents KeyError)
    chat_state = gr.State([])  # list of {"role","content"} dictionaries

    # ----- Header -----
    gr.HTML("""
    <div class="header-card">
      <div style="display:flex; align-items:center; gap:14px;">
        <div style="font-size:26px;">🛒🛡️</div>
        <div>
          <div style="font-weight:700; font-size:18px; letter-spacing:0.3px;">Click Kart ReclaimBot</div>
          <div style="opacity:0.8; font-size:13px;">Refund Assistant • Secure • Fast</div>
        </div>
      </div>
    </div>
    """)

    with gr.Row():
        # ----- Left: Chat area -----
        with gr.Column(scale=7, min_width=640):

            # Conversation box
            chatbot = gr.Chatbot(
                label="Conversation",
                height=375,               # was 500; now 375
                show_copy_button=True,
                type="messages",          # [{"role": "...", "content": "..."}]
            )

            # Input row BELOW the conversation box
            with gr.Row():
                user_input = gr.Textbox(
                    label="Your message",
                    placeholder="Ask about refunds, purchases, or eligibility… (Press Enter to send)",
                    lines=1,               # single-line so Enter submits
                    scale=5,
                    autofocus=True,
                )
                send_btn = gr.Button("Send", variant="primary", scale=1)

            # Keep clear + loader below the input row
            with gr.Row():
                clear_btn = gr.Button("Clear", variant="secondary", scale=1)
                loading = gr.HTML("<div class='loader'>Thinking…</div>", visible=False)

            gr.Examples(
                examples=[
                    "Sample : My name is David and My Package was Damaged"
                ],
                inputs=[user_input],
                label="Example Prompt for Refund Request",
            )

        # ----- Right: Info / Controls -----
        with gr.Column(scale=5, min_width=360):
            with gr.Tab("Agent Info"):
                gr.HTML(f"""
                <div class="side-card">
                  <div style="font-weight:600; margin-bottom:8px;">Runtime Info</div>
                  <div style="font-size:13px; line-height:1.6;">
                    <div>Model: <b>{GEMINI_MODEL}</b></div>
                    <div>App: <b>{app_name}</b></div>
                  </div>
                </div>
                """)
            with gr.Tab("About"):
                gr.HTML("""
                <div class="side-card">
                  <div style="font-weight:600; margin-bottom:8px;">What this app does</div>
                  <div style="font-size:13px; opacity:0.9; line-height:1.7;">
                    <ul style="margin: 8px 0 0 18px;">
                      <li>This is a <b>ReclaimBot for Click Kart Online</b> .</li>
                      <li>Which Verifies <b>Customer Name and Order</b> and <b>Checks Eligibility for Refund</b>.</li>
                      <li>If <b>Refund Eligibility meets Criteria</b>, then Refund is issued and a confirmation email is sent.</li>
                    </ul>
                  </div>
                </div>
                """)

    # ----- Events -----
    # Show spinner (disable button) → run chat → sync state → hide spinner
    send_btn.click(
        fn=show_working,
        inputs=[],
        outputs=[loading, send_btn],
        queue=False
    ).then(
        fn=chat,
        inputs=[user_input, chat_state],
        outputs=[chatbot, user_input],
        queue=True
    ).then(
        fn=lambda hist: hist,  # keep state in sync with what's rendered
        inputs=[chatbot],
        outputs=[chat_state],
        queue=False
    ).then(
        fn=hide_working,
        inputs=[],
        outputs=[loading, send_btn],
        queue=False
    )

    # Enter to submit (works because lines=1 and we bind the submit event)
    user_input.submit(
        fn=show_working,
        inputs=[],
        outputs=[loading, send_btn],
        queue=False
    ).then(
        fn=chat,
        inputs=[user_input, chat_state],
        outputs=[chatbot, user_input],
        queue=True
    ).then(
        fn=lambda hist: hist,
        inputs=[chatbot],
        outputs=[chat_state],
        queue=False
    ).then(
        fn=hide_working,
        inputs=[],
        outputs=[loading, send_btn],
        queue=False
    )

    clear_btn.click(
        fn=clear_chat,
        inputs=[],
        outputs=[chatbot, chat_state],
        queue=False
    )

    # Footer
    gr.HTML("""
    <div style="opacity:0.6; font-size:12px; text-align:center; margin-top:8px;">
      ✨ Powered by Gemini multi-agent workflow — Parallel sub-agents with sequential parent flow.
    </div>
    """)

demo.launch()
