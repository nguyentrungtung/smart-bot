# Product Requirements (MVP)

See `docs/PRD-Smart-Bot-MVP.md` for the original Product Requirements Document.

## Summary Checklist for Completion
- [ ] UI: Embeddable Preact `<script>` tag that injects a responsive `iframe` widget.
- [ ] UI: Widget detects content height and uses 2-way `postMessage` to auto-resize the iframe container dynamically.
- [ ] UI: Visual "Thinking" accordion that streams the AI's internal thought process separate from the final chat.
- [ ] MultiModal: Secure file upload validating strictly for Voice (`webm` -> converted to `wav/mp3` via FFmpeg buffer), Images (JPEG/PNG up to 5MB), and Text.
- [ ] Pipeline: PII Scrubber Middleware masking passwords/phones dynamically before fetching LLMs.
- [ ] RAG: Database vectors synced nightly from external RAGFlow instance. 0.7 Confidence hallucination block.
- [ ] Tools: At least 1 active MCP server executing the `Xweb Creation` action, guarded by a Telegram webhook HITL pause.
- [ ] Tools: A basic utility MCP server returning current Real-Time Date/Time and City Weather (via `geocoding-api.open-meteo.com` & `api.open-meteo.com`).
