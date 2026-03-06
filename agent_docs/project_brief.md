# Smart-Bot Project Brief

**Goal**: Build an enterprise-grade AI advisor and internal action-executor widget that sits on the company's production website.

## Key Stakeholders
1. **Public Customers**: Use the widget to ask questions via Voice/Text or upload an image, expecting intelligent, accurate answers about Xweb, ISO, and other company products pulled strictly from RAG.
2. **Internal Employees**: Can use it for internal documentation lookup.
3. **Managers**: Use the Human-In-The-Loop (HITL) Telegram bot or API dashboard to explicitly approve or deny sensitive tool actions (like creating an Xweb instance) that the bot has prepared.

## The Vibe
- **State-of-the-Art Enterprise**: Real-time websocket streaming, visible `<thinking>` accordion UI, no hallucinations, and uncrackable widget isolation. 
- **Highly Resilient**: Handles dropped 4G connections gracefully (streaming recovery), scales horizontally automatically via Redis queues, and strictly limits database connections via pooling.
