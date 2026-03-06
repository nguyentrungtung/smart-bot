# Product Requirements Document (PRD): Smart-Bot MVP

## 1. Product Overview
**Name**: Smart-Bot
**Vision**: An enterprise-grade, highly secure AI agent platform that serves as both a 24/7 intelligent sales advisor and a powerful internal action-executor across the company's software ecosystem.

## 2. Problem Statement
Smart-Bot solves the bottleneck of product consultation and tedious manual workflows by dynamically answering complex customer queries about existing products (ISO certificates, Xweb, POS, etc.) while autonomously executing real software actions (e.g., website creation) directly within the company's ecosystem.

## 3. Launch Goal
**Target Timeline**: Launch directly on the official production website next month.

## 4. Target Users
1. **External Customers (Website Visitors)**: Users looking to purchase ISO certifications, Xweb platforms, CRM, or POS systems. They need fast, accurate consultation and immediate automated onboarding (e.g., auto-generating a website).
2. **Internal Employees**: Staff who need to rapidly query internal documentation, manuals, and troubleshooting guides to support their daily work.

## 5. User Journey
1. **Customer Journey**: A visitor lands on the official site, opens the Smart-Bot widget, and asks (via voice or text) for details about the Xweb product. Smart-Bot uses RAG to explain the features, then the visitor uploads an image of a layout they like. Smart-Bot analyzes the image, triggers an MCP tool to automatically create an Xweb instance matching those specs, and pauses for human confirmation (HITL) before processing the final deployment.
2. **Employee Journey**: An employee logs into the internal portal, opens the Smart-Bot widget, and asks for the latest standard operating procedure for handling a CRM database migration. Smart-Bot instantly retrieves the precise document via vector search (RAG) and summarizes the steps.

## 6. MVP Core Features (Must-Haves)
1. **Multimodal Chat Interface**: Full support for Text, Voice (Speech-to-Text and Text-to-Speech via Socket.IO), and Vision (Image upload and analysis via LLMs like GPT-4o).
2. **Real-time Stream Parsing (<thinking>)**: The UI natively parses and hides the AI's internal reasoning loop inside an expandable "Thought Process" block to keep the chat clean.
3. **RAG Knowledge Lookup**: Deep native vector search utilizing PostgreSQL (`pgvector`) and RAGFlow to answer complex questions about products and internal documents.
4. **Action Execution (External & Utility Integration)**: 
   - **Xweb Creation**: Functional MCP tool server for interfacing with the company's ecosystem.
   - **Utility Tools**: Basic MCP tools for fetching strictly real-time contextual data (Current Server Time/Date, and Real-Time Weather via open-meteo API).
5. **Secure Isolated Widget**: An embeddable JS widget enclosed within a secure iframe to prevent cross-site scripting (XSS) and maintain strict isolation on production websites.

## 7. Success Metrics
- **Customer Engagement**: Increase in the number of leads generated or automated tasks (e.g., Xweb instances created) initiated by the bot.
- **Accuracy**: A high retrieval success rate from the RAG pipeline when answering specific product FAQs.
- **Latency**: Voice/TTS streaming latency under 2 seconds.

## 8. Technical Considerations
- **Architecture**: Decoupled microservices pattern.
- **Core Stack**: LangChain v1.2.0+, LangGraph, Python 3.11+.
- **Database**: PostgreSQL with `pgvector`.
- **LLM Gateway**: LiteLLM (Primary: Local LM Studio; Fallback: OpenAI cloud).
- **Extensibility**: Tools must be built strictly to the Model Context Protocol (MCP) using the official SDK over SSE.

## 9. Constraints
- **Security**: Must enforce strict isolation (`iframe`) to prevent tampering by frontend users.
- **Performance**: Must handle high Concurrent Users (CCU) effectively using asynchronous frameworks (Socket.IO, Celery) and scalable VPS infrastructure.

## 10. Definition of Done (MVP)
- [ ] Widget successfully embedded via iframe on a staging website.
- [ ] Users can chat using Text, Voice, or upload an Image, and receive accurate responses.
- [ ] Backend properly parses `<thinking>` tags and streams them to an isolated UI component.
- [ ] RAG pipeline correctly answers queries based on uploaded company documents.
- [ ] The bot can successfully trigger a simulated or live "Create Xweb" action via an MCP server.
