import streamlit as st
from openai import OpenAI
import time
import logging
import PyPDF2
from anthropic import Anthropic
import json
import os
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
import io
import requests
import firebase_admin
from firebase_admin import initialize_app
from firebase_admin import credentials
from firebase_admin import storage
from io import BytesIO
import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Initialize session state variables
if "messages" not in st.session_state:
    st.session_state.messages = []

if "assistant" not in st.session_state:
    st.session_state.assistant = client.beta.assistants.retrieve(st.secrets["AYUDAS_QUESTION_ASSISTANT_ID"])

if "thread" not in st.session_state:
    st.session_state.thread = client.beta.threads.create()

if "email" not in st.session_state:
    st.session_state.email = ""

if "info_pdf" not in st.session_state:
    st.session_state.info_pdf = None

if "annual_accounts" not in st.session_state:
    st.session_state.annual_accounts = None

if "processing_in_progress" not in st.session_state:
    st.session_state.processing_in_progress = False

# Add this new session state variable
if "welcome_message_displayed" not in st.session_state:
    st.session_state.welcome_message_displayed = False

# Set up the Streamlit page
st.set_page_config(page_title="Demo IA ayudas", layout="wide")

# Add custom CSS to set dark theme and style inputs
st.markdown("""
    <style>
    .stApp {
        background-color: #1E1E1E;
        color: white;
    }
    .stTextInput > div > div > input {
        background-color: #2D2D2D;
        color: white;
    }
    .stChatInput {
        background-color: #2D2D2D;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

# Title
st.title("Demo IA ayudas")

# Email input
email = st.text_input("Enter your email address:", key="email_input")
if email != st.session_state.email:
    st.session_state.email = email

# File uploads
info_pdf = st.file_uploader("Pdf informativo empresa:", type="pdf")
if info_pdf != st.session_state.info_pdf:
    st.session_state.info_pdf = info_pdf
    logging.info("Company info PDF uploaded")

annual_accounts = st.file_uploader("Cuentas Anuales:", type="pdf")
if annual_accounts != st.session_state.annual_accounts:
    st.session_state.annual_accounts = annual_accounts
    logging.info("Annual accounts PDF uploaded")

# Add this block after the file upload section and before the chat messages display
if not st.session_state.welcome_message_displayed:
    welcome_message = "¡Bienvenido! ¿Por qué necesita tu empresa el dinero de la subvención?"
    
    # Add to Streamlit chat display
    st.session_state.messages.append({"role": "assistant", "content": welcome_message})
    
    # Add to OpenAI thread
    client.beta.threads.messages.create(
        thread_id=st.session_state.thread.id,
        role="assistant",
        content=welcome_message
    )
    
    st.session_state.welcome_message_displayed = True
  
# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if not st.session_state.processing_in_progress:
    user_input = st.chat_input("Explica por qué tu empresa necesita esta subvención...", key="chat_input")
    if user_input:
        logging.info("User input received")
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Add the user's message to the thread
        client.beta.threads.messages.create(
            thread_id=st.session_state.thread.id,
            role="user",
            content=user_input
        )

        # Create a run
        run = client.beta.threads.runs.create(
            thread_id=st.session_state.thread.id,
            assistant_id=st.session_state.assistant.id
        )

        # Flag to indicate when to exit the main loop
        exit_main_loop = False

        # Wait for the run to complete or require action
        while not exit_main_loop:
            logging.info(f"Checking run status. Thread ID: {st.session_state.thread.id}, Run ID: {run.id}")
            run_status = client.beta.threads.runs.retrieve(
                thread_id=st.session_state.thread.id,
                run_id=run.id
            )
            logging.info(f"Current run status: {run_status.status}")
            
            if run_status.status == 'completed':
                logging.info("Run completed successfully")
                break
            elif run_status.status == 'requires_action':
                logging.info("Run requires action")
                tool_calls = run_status.required_action.submit_tool_outputs.tool_calls
                for tool_call in tool_calls:
                    if tool_call.function.name == "generar_contrato":
                        logging.info("generar_contrato function called")
                        # Check if all required information is provided
                        if not st.session_state.email or not st.session_state.info_pdf or not st.session_state.annual_accounts:
                            logging.warning("Missing required information")
                            st.error("Por favor, proporciona toda la información requerida antes de procesar.")
                            exit_main_loop = True
                            break

                        logging.info("Starting document processing")
                        processing_message = "El procesamiento de documentos ha comenzado. Por favor, espera..."
                        st.session_state.messages.append({"role": "assistant", "content": processing_message})
                        with st.chat_message("assistant"):
                            st.markdown(processing_message)
                        
                        st.session_state.processing_in_progress = True
                        
                        client.beta.threads.runs.cancel(
                                thread_id=st.session_state.thread.id,
                                run_id=run.id,
                                
                            )
                        
                        logging.info("Starting document generation")
                        try:
                            result = generar_contrato(
                                st.session_state.email, 
                                st.session_state.info_pdf, 
                                st.session_state.annual_accounts,
                                st.session_state.thread.id
                            )
                            logging.info("Document generation completed successfully")
                            
                            # Submit the tool outputs
                            
                            
                        except Exception as e:
                            logging.error(f"Error during document generation: {str(e)}")
                            st.error("Hubo un error durante la generación del documento. Por favor, inténtalo de nuevo.")
                        
                        completed_message = f"Los documentos han sido enviados a tu mail: {st.session_state.email}."
                        st.session_state.messages.append({"role": "assistant", "content": completed_message})
                        with st.chat_message("assistant"):
                            st.markdown(completed_message)
                        
                        st.session_state.processing_in_progress = False
                        exit_main_loop = True
                        break  # Exit the for loop

                if exit_main_loop:
                    break  # Exit the while loop if processing started

            elif run_status.status in ['failed', 'cancelled', 'expired']:
                logging.error(f"Run failed with status: {run_status.status}")
                break
            
            logging.info("Waiting before next status check")
            time.sleep(1)

        logging.info("Exited main processing loop")

# Retrieve and display only the latest assistant message
messages = client.beta.threads.messages.list(
    thread_id=st.session_state.thread.id,
    order="desc",
    limit=1
)

for message in messages.data:
    if message.role == "assistant" and message.content[0].type == "text":
        assistant_response = message.content[0].text.value
        logging.info("New assistant response received")
        if not st.session_state.messages or st.session_state.messages[-1]["role"] != "assistant":
            st.session_state.messages.append({"role": "assistant", "content": assistant_response})
            with st.chat_message("assistant"):
                st.markdown(assistant_response)

# If processing has started, display a message
if st.session_state.processing_in_progress:
    st.info("El procesamiento ha comenzado. Por favor, espera los resultados.")