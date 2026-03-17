import asyncio
import psycopg
import logging
from langgraph.checkpoint.postgres import PostgresSaver
from app.workflows.graph import workflow

logging.basicConfig(level=logging.ERROR)

async def check_multimodal_cleanup():
    async with await psycopg.AsyncConnection.connect("postgresql://admin:admin@localhost:5432/smartsales") as conn:
        checkpointer = PostgresSaver(conn)
        
        # Find latest thread_id
        async with conn.cursor() as cur:
            await cur.execute("SELECT thread_id FROM checkpoints ORDER BY checkpoint_id DESC LIMIT 1")
            row = await cur.fetchone()
            if not row:
                print("No threads found.")
                return
            thread_id = row[0]
            print(f"Checking thread: {thread_id}")

        config = {"configurable": {"thread_id": thread_id}}
        state = await checkpointer.aget(config)
        
        if not state:
            print("State not found.")
            return

        messages = state['channel_values'].get('messages', [])
        found_multimodal = False
        for i, m in enumerate(messages):
            from langchain_core.messages import HumanMessage
            if isinstance(m, HumanMessage):
                if isinstance(m.content, list):
                    found_multimodal = True
                    print(f"Message {i} is STILL MULTIMODAL!")
                    for block in m.content:
                        print(f"  Block type: {block.get('type')}")
                        if 'image_url' in block:
                            print(f"  Image data len: {len(str(block['image_url']))}")
                elif "[MÔ TẢ ĐA PHƯƠNG TIỆN]" in str(m.content):
                    print(f"Message {i} is SCRUBBED (Text description found ✅)")
                else:
                    print(f"Message {i} is normal text.")

        if not found_multimodal:
            print("\nRESULT: Memory is clean! No multimodal blocks found.")
        else:
            print("\nRESULT: Multimodal blocks are STILL PRESENT in memory.")

if __name__ == "__main__":
    asyncio.run(check_multimodal_cleanup())
