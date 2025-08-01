# Langchain Models (legacy)

This directory contains example of how to still use Langchain models with the new Browser Use chat models.

## How to use

```python
from langchain_openai import ChatOpenAI

from browser_use import Agent
from .chat import ChatLangchain

async def main():
	"""Basic example using ChatLangchain with OpenAI through LangChain."""

	# Create a LangChain model (OpenAI)
	langchain_model = ChatOpenAI(
		model='gpt-4.1-mini',
		temperature=0.1,
	)

	# Wrap it with ChatLangchain to make it compatible with browser-use
	llm = ChatLangchain(chat=langchain_model)

    agent = Agent(
        task="Go to google.com and search for 'browser automation with Python'",
        llm=llm,
    )

    history = await agent.run()

    print(history.history)
```

## Using with OpenAI-compatible APIs

Some OpenAI-compatible APIs may not support the `json_schema` response format. If you encounter errors like:

```
Invalid parameter: 'response_format' of type 'json_schema' is not supported with this model
```

You can disable structured output and rely on manual JSON parsing:

```python
from langchain_openai import ChatOpenAI
from browser_use import Agent
from .chat import ChatLangchain

async def main():
    # Create a LangChain model pointing to an OpenAI-compatible API
    langchain_model = ChatOpenAI(
        model='gpt-4o',
        api_key='your-api-key',
        base_url='https://your-api-endpoint.com/v1'
    )

    # Wrap it with ChatLangchain and disable structured output
    llm = ChatLangchain(
        chat=langchain_model,
        disable_structured_output=True  # This avoids json_schema errors
    )

    agent = Agent(
        task="Your task here",
        llm=llm,
    )

    history = await agent.run()
```

## Features

- **Structured Output Support**: By default, ChatLangchain will try to use LangChain's structured output features when available
- **Automatic Fallback**: If structured output fails, it automatically falls back to manual JSON parsing
- **Compatibility Mode**: Use `disable_structured_output=True` for APIs that don't support OpenAI's structured output features
- **Error Handling**: Clear error messages guide you when compatibility issues arise

## Supported Models

ChatLangchain works with any LangChain chat model, including:
- OpenAI models (ChatOpenAI)
- Anthropic models (ChatAnthropic)
- Google models (ChatGoogleGenerativeAI)
- Groq models (ChatGroq)
- Ollama models (ChatOllama)
- DeepSeek models
- Any other LangChain-compatible chat model
