from langchain_deepseek import ChatDeepSeek

from config.load_variables import (
    DEEPSEEK_API_KEY
)


def get_deepseek():

    return ChatDeepSeek(
        model="deepseek-chat",
        api_key=DEEPSEEK_API_KEY,
        temperature=0
    )

