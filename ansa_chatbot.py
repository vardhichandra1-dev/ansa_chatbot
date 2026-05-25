"""
ANSA Embedded Chatbot
======================
A fully dockable chat panel built inside ANSA using BCGui (guitk).
The chatbot connects to a FastAPI + LangGraph backend (or falls back
to direct OpenAI API) and can auto-execute generated ANSA scripts.

ARCHITECTURE:
    ANSA BCGui Panel  -->  HTTP POST  -->  FastAPI + LangGraph  -->  LLM
                      <--  Script JSON <--                      <--

HOW TO RUN IN ANSA:
    1. Make sure your FastAPI backend is running on localhost:8000
       (or set USE_DIRECT_LLM = True to call OpenAI directly)
    2. Open ANSA
    3. Go to: Scripts > Run Script > select this file
    4. Chat panel appears docked inside ANSA
"""

import ansa
from ansa import base, constants, guitk
import requests
import json
import threading
import os

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

# Set to True to call OpenAI directly (no FastAPI backend needed)
USE_DIRECT_LLM = False

# FastAPI backend URL (used when USE_DIRECT_LLM = False)
FASTAPI_URL = 'http://localhost:8000/generate'

# OpenAI API key (used when USE_DIRECT_LLM = True)
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', 'your-api-key-here')

# Session ID for multi-turn memory in LangGraph
SESSION_ID = 'ansa_session_001'


# ─────────────────────────────────────────────
# BACKEND COMMUNICATION
# ─────────────────────────────────────────────

def call_fastapi_backend(user_prompt: str) -> dict:
    """
    Sends user prompt to FastAPI + LangGraph backend.
    Returns dict with 'script' and 'explanation' keys.
    """
    try:
        response = requests.post(
            FASTAPI_URL,
            json={
                'prompt': user_prompt,
                'session_id': SESSION_ID
            },
            timeout=60
        )
        response.raise_for_status()
        return response.json()

    except requests.exceptions.ConnectionError:
        return {
            'script': None,
            'explanation': 'Could not connect to FastAPI backend. '
                           'Make sure your server is running on localhost:8000.'
        }
    except requests.exceptions.Timeout:
        return {
            'script': None,
            'explanation': 'Request timed out. The LLM might be processing a complex query.'
        }
    except Exception as e:
        return {
            'script': None,
            'explanation': f'Backend error: {str(e)}'
        }


def call_openai_direct(user_prompt: str) -> dict:
    """
    Calls OpenAI API directly (fallback when no FastAPI backend).
    Returns dict with 'script' and 'explanation' keys.
    """
    try:
        headers = {
            'Authorization': f'Bearer {OPENAI_API_KEY}',
            'Content-Type': 'application/json'
        }
        payload = {
            'model': 'gpt-4',
            'messages': [
                {
                    'role': 'system',
                    'content': (
                        'You are an expert ANSA CAE automation engineer. '
                        'When asked to perform ANSA operations, respond with: '
                        '1) A brief explanation of what you will do. '
                        '2) A complete Python script using only ansa.base and ansa.constants APIs. '
                        'Always import ansa and from ansa import base, constants.'
                    )
                },
                {
                    'role': 'user',
                    'content': user_prompt
                }
            ],
            'max_tokens': 1000
        }
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        content = response.json()['choices'][0]['message']['content']

        # Try to extract script from response
        script = None
        if '```python' in content:
            start = content.find('```python') + 9
            end = content.find('```', start)
            script = content[start:end].strip()

        return {
            'script': script,
            'explanation': content
        }

    except Exception as e:
        return {
            'script': None,
            'explanation': f'OpenAI API error: {str(e)}'
        }


def get_llm_response(user_prompt: str) -> dict:
    """
    Routes to FastAPI backend or direct OpenAI based on config.
    """
    if USE_DIRECT_LLM:
        return call_openai_direct(user_prompt)
    else:
        return call_fastapi_backend(user_prompt)


# ─────────────────────────────────────────────
# ANSA SCRIPT EXECUTION
# ─────────────────────────────────────────────

def execute_ansa_script(script: str) -> str:
    """
    Writes generated script to temp file and executes it in ANSA.
    Returns execution status message.
    """
    try:
        script_path = '/tmp/ansa_chatbot_gen.py'
        with open(script_path, 'w') as f:
            f.write(script)

        # Native ANSA script execution
        base.ExecuteScript(script_path)
        return 'Script executed successfully in ANSA.'

    except Exception as e:
        return f'Script execution failed: {str(e)}'


def get_model_context() -> str:
    """
    Reads live ANSA model state to enrich prompts with context.
    """
    try:
        deck = base.CurrentDeck()
        parts = base.CollectEntities(deck, None, 'PART')
        shells = base.CollectEntities(deck, None, 'SHELL')

        part_count = len(parts) if parts else 0
        shell_count = len(shells) if shells else 0

        return (
            f'[Model context: {part_count} parts, '
            f'{shell_count} shell elements, '
            f'deck: {str(deck)}]'
        )
    except Exception:
        return '[Model context: unavailable]'


# ─────────────────────────────────────────────
# CHAT HISTORY
# ─────────────────────────────────────────────

chat_history = []  # List of (role, message) tuples


def format_chat_display() -> str:
    """
    Formats chat history for display in the text area.
    """
    lines = []
    for role, message in chat_history[-10:]:  # Show last 10 messages
        prefix = 'You: ' if role == 'user' else 'ANSA AI: '
        lines.append(f'{prefix}{message}')
        lines.append('')  # Empty line between messages
    return '\n'.join(lines)


# ─────────────────────────────────────────────
# GUI: ANSA CHATBOT PANEL
# ─────────────────────────────────────────────

def build_chatbot_panel():
    """
    Builds a dockable chatbot panel inside ANSA using BCGui (guitk).

    Layout:
    ┌──────────────────────────────┐
    │  ANSA AI Assistant           │
    ├──────────────────────────────┤
    │  [Chat history display area] │
    │                              │
    ├──────────────────────────────┤
    │  [Text input field]          │
    │  [Send]  [Execute Script]    │
    └──────────────────────────────┘
    """

    # ── Main Window ──
    window = guitk.BCWindow(
        'ANSA AI Assistant',
        guitk.constants.BCWindowFlagType.BCNoFlag
    )
    window.setFixedSize(420, 480)

    # ── Main Layout ──
    main_layout = guitk.BCBoxLayout(
        guitk.constants.BCOrientationType.BCVertical
    )

    # ── Title ──
    title_label = guitk.BCLabel('ANSA AI Chatbot')
    title_label.setFont(guitk.BCFont('Arial', 12, True))
    main_layout.addWidget(title_label)

    model_ctx_label = guitk.BCLabel(get_model_context())
    model_ctx_label.setFont(guitk.BCFont('Arial', 8, False))
    main_layout.addWidget(model_ctx_label)

    main_layout.addSpacing(8)

    # ── Chat Display Area ──
    chat_display = guitk.BCTextEdit()
    chat_display.setReadOnly(True)
    chat_display.setFixedHeight(240)
    chat_display.setPlainText('Hello! Ask me anything about your ANSA model.\n')
    main_layout.addWidget(chat_display)

    main_layout.addSpacing(8)

    # ── Status Label ──
    status_label = guitk.BCLabel('Ready.')
    status_label.setFont(guitk.BCFont('Arial', 8, False))
    main_layout.addWidget(status_label)

    main_layout.addSpacing(6)

    # ── Input Field ──
    input_field = guitk.BCLineEdit()
    input_field.setPlaceholderText('Type your question here...')
    main_layout.addWidget(input_field)

    main_layout.addSpacing(6)

    # ── Buttons Layout ──
    btn_layout = guitk.BCBoxLayout(
        guitk.constants.BCOrientationType.BCHorizontal
    )

    # Store last generated script for execution
    last_script = {'value': None}

    # ── Send Button Handler ──
    def on_send():
        user_text = input_field.text().strip()
        if not user_text:
            return

        # Add to history and update display
        chat_history.append(('user', user_text))
        chat_display.setPlainText(format_chat_display())
        input_field.setText('')
        status_label.setText('Thinking...')

        # Run LLM call in background thread to avoid freezing ANSA UI
        def background_call():
            # Enrich prompt with live model context
            enriched_prompt = (
                f'{get_model_context()}\n\nUser request: {user_text}'
            )
            result = get_llm_response(enriched_prompt)

            explanation = result.get('explanation', 'No response received.')
            script = result.get('script')

            # Store script for execution button
            last_script['value'] = script

            # Truncate long explanations for display
            display_text = explanation[:300] + '...' if len(explanation) > 300 else explanation

            # Update UI (must be done carefully in ANSA's thread)
            chat_history.append(('assistant', display_text))
            chat_display.setPlainText(format_chat_display())

            if script:
                status_label.setText(
                    'Script ready. Click "Execute in ANSA" to run it.'
                )
            else:
                status_label.setText('Response received. No script generated.')

        thread = threading.Thread(target=background_call, daemon=True)
        thread.start()

    # ── Execute Script Button Handler ──
    def on_execute():
        if last_script['value'] is None:
            status_label.setText('No script to execute. Send a message first.')
            return

        status_label.setText('Executing script in ANSA...')
        result = execute_ansa_script(last_script['value'])
        status_label.setText(result)

        # Log execution in chat
        chat_history.append(('assistant', f'[Executed] {result}'))
        chat_display.setPlainText(format_chat_display())

    # ── Clear Button Handler ──
    def on_clear():
        chat_history.clear()
        last_script['value'] = None
        chat_display.setPlainText(
            'Chat cleared. Hello! Ask me anything about your ANSA model.\n'
        )
        status_label.setText('Ready.')

    # ── Create Buttons ──
    send_btn = guitk.BCPushButton('Send')
    send_btn.onClicked(on_send)

    execute_btn = guitk.BCPushButton('Execute in ANSA')
    execute_btn.onClicked(on_execute)

    clear_btn = guitk.BCPushButton('Clear')
    clear_btn.onClicked(on_clear)

    btn_layout.addWidget(send_btn)
    btn_layout.addWidget(execute_btn)
    btn_layout.addWidget(clear_btn)

    main_layout.addLayout(btn_layout)

    # ── Attach layout and show ──
    window.setLayout(main_layout)
    window.show()


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == '__main__':
    build_chatbot_panel()
