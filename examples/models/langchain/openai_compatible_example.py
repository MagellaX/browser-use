"""
Example of using LangChain models with OpenAI-compatible APIs that don't support json_schema.

This example demonstrates how to use the ChatLangchain wrapper with disable_structured_output=True
to avoid json_schema errors when using APIs like aihubmix.com or other OpenAI proxies.

This solves issue #241: https://github.com/browser-use/browser-use/issues/241
"""
import asyncio
import os

from langchain_openai import ChatOpenAI
from browser_use import Agent
from examples.models.langchain.chat import ChatLangchain


async def main():
    """Example using ChatLangchain with OpenAI-compatible APIs."""
    
    # Create a LangChain model pointing to an OpenAI-compatible API
    # Replace with your actual API endpoint and key
    langchain_model = ChatOpenAI(
        model='gpt-4o',  # or any model supported by your API
        api_key=os.environ.get('OPENAI_API_KEY', 'your-api-key'),
        base_url=os.environ.get('OPENAI_API_BASE', 'https://aihubmix.com/v1')
    )
    
    # Wrap it with ChatLangchain and disable structured output
    # This is crucial for APIs that don't support json_schema response format
    llm = ChatLangchain(
        chat=langchain_model,
        disable_structured_output=True  # Avoids json_schema errors!
    )
    
    # Create your task
    task = "Go to google.com and search for 'browser automation with Python'"
    
    # Create and run the agent
    agent = Agent(
        task=task,
        llm=llm,
    )
    
    print(f'🚀 Starting task: {task}')
    print(f'🤖 Using model: {llm.name} via {langchain_model.openai_api_base}')
    print(f'⚙️  Structured output disabled: {llm.disable_structured_output}')
    
    try:
        # Run the agent
        history = await agent.run()
        
        print(f'\n✅ Task completed successfully!')
        print(f'📊 Steps taken: {len(history.history)}')
        
        # Print the final result if available
        if history.final_result():
            print(f'📋 Final result: {history.final_result()}')
    
    except Exception as e:
        print(f'\n❌ Error occurred: {type(e).__name__}: {str(e)}')
        
        # Check if it's a json_schema error
        if "json_schema" in str(e) or "response_format" in str(e):
            print("\n💡 Tip: Make sure you're using ChatLangchain with disable_structured_output=True")
            print("   This avoids json_schema errors with OpenAI-compatible APIs.")


if __name__ == '__main__':
    print('🌐 Browser-use with OpenAI-compatible APIs Example')
    print('=' * 50)
    print('This example shows how to use LangChain models with APIs')
    print('that don\'t support OpenAI\'s json_schema response format.')
    print('=' * 50)
    
    asyncio.run(main())