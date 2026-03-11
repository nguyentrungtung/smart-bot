import litellm
import os

def test_gemini():
    print("Testing direct call to gemini-2.5-flash via LiteLLM...")
    try:
        response = litellm.completion(
            model="openai/gemini-2.5-flash", # Proxy name for mapped gemini
            messages=[{"role": "user", "content": "Explain quantum physics briefly."}],
            api_base="http://localhost:4000",
            api_key="sk-litellm-proxy"
        )
        print("Success!")
        print(f"Response: {response.choices[0].message.content}")
    except Exception as e:
        print(f"Failed with error: {type(e).__name__}: {str(e)}")

if __name__ == "__main__":
    test_gemini()
