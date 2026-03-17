import psycopg

def check_latest_blob():
    try:
        conn = psycopg.connect("postgresql://admin:admin@localhost:5432/smartsales")
        cur = conn.cursor()
        
        # Get the latest thread and its latest checkpoint
        cur.execute("SELECT thread_id, checkpoint_id FROM checkpoints ORDER BY checkpoint_id DESC LIMIT 1")
        res = cur.fetchone()
        if not res:
            print("No checkpoints found.")
            return
        
        thread_id, cp_id = res
        print(f"Checking Thread: {thread_id}, Checkpoint: {cp_id}")
        
        # Get all blobs for this checkpoint
        cur.execute("SELECT type, blob FROM checkpoint_blobs WHERE thread_id = %s", (thread_id,))
        blobs = cur.fetchall()
        
        total_size = 0
        has_image = False
        for type_name, blob_data in blobs:
            total_size += len(blob_data)
            if b"data:image" in blob_data:
                has_image = True
                print(f"  -> Blob (type: {type_name}) contains raw image data (Size: {len(blob_data)} bytes)")
        
        if not has_image:
            print(f"✅ SUCCESS: No raw image data found in the latest thread state. Total state size: {total_size} bytes.")
        else:
            print(f"❌ FAIL: Raw image data is still present in the latest thread state.")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_latest_blob()
