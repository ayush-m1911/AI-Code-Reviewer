import os
import time
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

_base_llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0
)

class WrappedChatGroq:
    def __init__(self, target_llm):
        self._llm = target_llm

    def invoke(self, prompt, *args, **kwargs):
        max_retries = 6
        delay = 4
        for attempt in range(max_retries):
            try:
                return self._llm.invoke(prompt, *args, **kwargs)
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "rate limit" in err_str.lower():
                    print(f"\n[Rate Limit] Groq rate limit hit. Retrying in {delay} seconds... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(delay)
                    delay = delay * 2 + 1
                else:
                    raise e
        return self._llm.invoke(prompt, *args, **kwargs)

llm = WrappedChatGroq(_base_llm)