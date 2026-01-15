# Chatbot for Library

## Introduction 
- This is a library assistant chatbot project. The chatbot can interact with users to advise on books, look up information, and support library users. The goal of the project is to automate basic customer care processes, enhance user experience, and reduce the workload for librarians.
- This is a product researched and developed by the R&D team at `AICI GLOBAL`.

## Architecture
The system is designed with a Multi-agent architecture, where each agent specializes in a specific task and is coordinated by a supervisor agent.

## Used Technology
- **Backend Framework**: `FastAPI`
- **LLM Framework**: `LangChain`, `LangGraph`
- **Large Language Models (LLM)**: `OpenAI (GPT-4, GPT-3.5)`
- **Database**: `Supabase (PostgreSQL)`

## Installation Guide
1. **Clone repository to your machine:**
```
git clone <your-repository-url>
cd Chatbot_ThuVien
```
2. **Create and activate a virtual environment:**
```
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
```

3. **Install necessary dependencies:**
```
pip install -r requirements.txt
```

4. **Configure environment variables:**
Create a `.env` file in the project's root directory and fill in the necessary information.

5. **Run the application:**
Use uvicorn to start the FastAPI server.
```
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
