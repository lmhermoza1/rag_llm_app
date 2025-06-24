import os
os.environ["USER_AGENT"] = "rag-llm-app/1.0"  # Set before any other imports

import streamlit as st
from streamlit_msal import Msal
import requests
import dotenv
dotenv.load_dotenv()
from PIL import Image
from io import BytesIO
import base64
import uuid

# check if it's linux so it works on Streamlit Cloud
if os.name == 'posix':
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain.schema import HumanMessage, AIMessage

from rag_methods import (
    load_doc_to_db, 
    load_url_to_db,
    stream_llm_response,
    stream_llm_rag_response,
)

# --- THIS MUST BE THE FIRST STREAMLIT COMMAND ---
st.set_page_config(
    page_title="Chat your way", 
    page_icon="📚", 
    layout="centered", 
    initial_sidebar_state="expanded"
)

# Configuration for MSAL
#CLIENT_ID = os.getenv("MS_CLIENT_ID")
#TENANT_ID = os.getenv("MS_TENANT_ID")
#AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
#REDIRECT_URI = os.getenv("MS_REDIRECT_URI", "http://localhost:8501")

#client_id = "b328b431-8532-4d1b-9e4c-0280bf0ee08f"
#tenant_id = "4b8684a0-11a0-4d2c-bddb-b90d7e931c35"

client_id = "b328b431-8532-4d1b-9e4c-0280bf0ee08f"
tenant_id = "4b8684a0-11a0-4d2c-bddb-b90d7e931c35"

# Define the Images logos path
path = 'assets/logos/'

# Authenticate user
auth_data = Msal.initialize(
    client_id=f"{client_id}",
    authority=f"https://login.microsoftonline.com/{tenant_id}",
    scopes=["User.Read"],  # Ask for a basic profile user info claim
)

# Get user info from Graph API    
def get_user_info(access_token):
    """Get user information from Microsoft Graph API."""
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get(
        'https://graph.microsoft.com/v1.0/me?$select=displayName,jobTitle,companyName,mail,userPrincipalName,officeLocation,state,givenName',
        headers=headers
    )
    if response.status_code == 200:
        return response.json()        
    return None

def get_user_photo(access_token):
    """Get user profile photo from Microsoft Graph API."""
    headers = {'Authorization': f'Bearer {access_token}'}
    try:
        response = requests.get(
            'https://graph.microsoft.com/v1.0/me/photo/$value',
            headers=headers
        )
        if response.status_code == 200:
            return response.content
        return None
    except Exception as e:
        return None
    
    page_title="Chat your way", 
    Msal.revalidate() # Usefull to refresh "accessToken"

if not auth_data:
    st.warning("Please sign in to access the app.")
    if st.button("Sign in"):
        Msal.sign_in() # Show popup to select account
    st.stop()
else:
    # User is authenticated - show sign out button in sidebar or at bottom
    access_token = auth_data["accessToken"]
    user_info = get_user_info(access_token)    
    user_photo = get_user_photo(access_token)

    #Match company logo
    logo_url = user_info.get('companyName') + ".PNG" 
    
    with st.sidebar:
        img = Image.open(path + logo_url)
        st.image(img, caption="", use_container_width=True)
        # Display user information
        if user_photo:
            try:
                img = Image.open(BytesIO(user_photo))
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                img_b64 = base64.b64encode(buffered.getvalue()).decode()
                img_html = f"""
                    <div style="text-align:center;">
                        <img src="data:image/png;base64,{img_b64}" 
                            style="width:100px;height:100px;border-radius:50%;object-fit:cover;border:2px solid #ddd;" />
                        <br> <strong>{user_info.get('displayName', 'N/A')}</strong><br>
                        {user_info.get('jobTitle', 'N/A')}<br>
                        {user_info.get('companyName', 'N/A')}
                    </div>
                """
                st.markdown(img_html, unsafe_allow_html=True)
                                    
            except Exception as e:
                    st.write("📷 Photo unavailable")
        else:
            st.write("📷 No photo available")
        
        st.write("")
        
        # Create two columns and place the buttons
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("Sign out"):
                Msal.sign_out() # Triggers sign-out process and reruns the app  
        with col2:
            if st.button("Refresh"):
                Msal.revalidate() # Triggers sign-out process and reruns the app 


if "AZ_OPENAI_API_KEY" not in os.environ:
    MODELS = [
        # "openai/o1-mini",
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "anthropic/claude-3-5-sonnet-20240620",
    ]
else:
    MODELS = ["azure-openai/gpt-4o"]

# --- Header ---
# st.html("""<h1 style="text-align: center;">Chat with your Data</h1>""")

image = Image.open('assets/phiai.png')
#st.image(image, caption='Sunrise')

# Create three columns and place the image in the center one
col1, col2, col3 = st.columns([1, 1, 1])
with col1:
    st.html("""<h1 style="text-align: right;">Chat with</h1>""")    
with col2:
    st.html("""<h1 style="text-align: left;">your Data Now!</h1>""")  
    st.image(image, width=120, caption="")
    
# with col3:
#    st.html("""<h1 style="text-align: left;">your Data</h1>""")  


# --- Initial Setup ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "rag_sources" not in st.session_state:
    st.session_state.rag_sources = []

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there! How can I assist you today?"}
]


# --- Side Bar LLM API Tokens ---
with st.sidebar:
    if "AZ_OPENAI_API_KEY" not in os.environ:
        default_openai_api_key = os.getenv("OPENAI_API_KEY") if os.getenv("OPENAI_API_KEY") is not None else ""  # only for development environment, otherwise it should return None
        with st.popover("🔐 OpenAI"):
            openai_api_key = st.text_input(
                "Introduce your OpenAI API Key (https://platform.openai.com/)", 
                value=default_openai_api_key, 
                type="password",
                key="openai_api_key",
            )

        default_anthropic_api_key = os.getenv("ANTHROPIC_API_KEY") if os.getenv("ANTHROPIC_API_KEY") is not None else ""
        with st.popover("🔐 Anthropic"):
            anthropic_api_key = st.text_input(
                "Introduce your Anthropic API Key (https://console.anthropic.com/)", 
                value=default_anthropic_api_key, 
                type="password",
                key="anthropic_api_key",
            )
    else:
        openai_api_key, anthropic_api_key = None, None
        st.session_state.openai_api_key = None
        az_openai_api_key = os.getenv("AZ_OPENAI_API_KEY")
        st.session_state.az_openai_api_key = az_openai_api_key


# --- Main Content ---
# Checking if the user has introduced the OpenAI API Key, if not, a warning is displayed
missing_openai = openai_api_key == "" or openai_api_key is None or "sk-" not in openai_api_key
missing_anthropic = anthropic_api_key == "" or anthropic_api_key is None
if missing_openai and missing_anthropic and ("AZ_OPENAI_API_KEY" not in os.environ):
    st.write("#")
    st.warning("⬅️ Please introduce an API Key to continue...")

else:
    # Sidebar
    with st.sidebar:
        st.divider()
        models = []
        for model in MODELS:
            if "openai" in model and not missing_openai:
                models.append(model)
            elif "anthropic" in model and not missing_anthropic:
                models.append(model)
            elif "azure-openai" in model:
                models.append(model)

        st.selectbox(
            "🤖 Select a Model", 
            options=models,
            key="model",
        )

        cols0 = st.columns(2)
        with cols0[0]:
            is_vector_db_loaded = ("vector_db" in st.session_state and st.session_state.vector_db is not None)
            st.toggle(
                "Use RAG", 
                value=is_vector_db_loaded, 
                key="use_rag", 
                disabled=not is_vector_db_loaded,
            )

        with cols0[1]:
            st.button("Clear Chat", on_click=lambda: st.session_state.messages.clear(), type="primary")

        st.header("RAG Sources:")
            
        # File upload input for RAG with documents
        st.file_uploader(
            "📄 Upload a document", 
            type=["pdf", "txt", "docx", "md"],
            accept_multiple_files=True,
            on_change=load_doc_to_db,
            key="rag_docs",
        )

        # URL input for RAG with websites
        st.text_input(
            "🌐 Introduce a URL", 
            placeholder="https://example.com",
            on_change=load_url_to_db,
            key="rag_url",
        )

        with st.expander(f"📚 Documents in DB ({0 if not is_vector_db_loaded else len(st.session_state.rag_sources)})"):
            st.write([] if not is_vector_db_loaded else [source for source in st.session_state.rag_sources])

    
    # Main chat app
    model_provider = st.session_state.model.split("/")[0]
    if model_provider == "openai":
        llm_stream = ChatOpenAI(
            api_key=openai_api_key,
            model_name=st.session_state.model.split("/")[-1],
            temperature=0.3,
            streaming=True,
        )
    elif model_provider == "anthropic":
        llm_stream = ChatAnthropic(
            api_key=anthropic_api_key,
            model=st.session_state.model.split("/")[-1],
            temperature=0.3,
            streaming=True,
        )
    elif model_provider == "azure-openai":
        llm_stream = AzureChatOpenAI(
            azure_endpoint=os.getenv("AZ_OPENAI_ENDPOINT"),
            openai_api_version="2024-12-01-preview",
            model_name=st.session_state.model.split("/")[-1],
            openai_api_key=os.getenv("AZ_OPENAI_API_KEY"),
            openai_api_type="azure",
            temperature=0.3,
            streaming=True,
        )

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Your message"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""

            messages = [HumanMessage(content=m["content"]) if m["role"] == "user" else AIMessage(content=m["content"]) for m in st.session_state.messages]

            if not st.session_state.use_rag:
                st.write_stream(stream_llm_response(llm_stream, messages))
            else:
                st.write_stream(stream_llm_rag_response(llm_stream, messages))


with st.sidebar:
    st.divider()
    st.video("https://youtu.be/abMwFViFFhI")
    st.write("📋[Medium Blog](https://medium.com/@enricdomingo/program-a-rag-llm-chat-app-with-langchain-streamlit-o1-gtp-4o-and-claude-3-5-529f0f164a5e)")
    st.write("📋[GitHub Repo](https://github.com/enricd/rag_llm_app)")

    
