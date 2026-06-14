# Cloud Services Take-Home Interview Question

Replit provides first party integrations that our users can use within their apps to seamlessly connect to AI services such OpenAI, Anthropic, and OpenRouter. This enables them to add AI features to their apps without setting up external accounts.

The way this works is that we have a single proxy server set up that all user requests go through. Each user has their own API token that uniquely identifies them. We track LLM token usage for each user and use it to control the billing relationship, including in-arrears billing and usage limits. LLM token cost is passed to users as-is.

Your task in this exercise will be to implement this proxy server.

### Requirements

- Download Ollama to your computer. For this exercise, we will be using the Llama 3.2 1B and moondream models. Download those with `ollama pull llama3.2` and `ollama pull moondream`.
- Using TypeScript, Go, or Python, implement a proxy server that listens to HTTP requests on port 8000 and forwards them to your local Ollama server.
- Ollama already has an OpenAI-compatible API. Your proxy server will sit on top of this API and implement some additional features, as specified below.
- You may take inspiration from open-source SDKs such as vLLM and Vercel AI SDK but all of the code for the proxy itself should be your own.
- AI coding tools are allowed. You are still expected to show a deep technical understanding of the code your tools generate and proof that your code works as intended.
- Some of the features are slightly ambiguous. Take note of how you make tradeoffs and decisions within the context of this implementation. Be prepared to defend why you chose one path over another.

### Implementation

1. Your server must be able to handle completions (including streaming) with Llama 3.2 1B, as well as vision processing with moondream. To get a test image, use Lorem Picsum. Use the `openai` library to test that your proxy server works as expected. For example, something like the following (or whatever the equivalent is in the language you choose).

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000",  # your proxy server
    api_key="..."
)

# Basic chat completion
response = client.chat.completions.create(
    model="llama3.2:1b",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is 2+2?"}
    ],
    temperature=0.7,
    max_tokens=100
)
```

1. Your proxy server should be able to handle lots of concurrent users. Demonstrate that your server can handle hundreds of requests per second.
2. We need to implement billing and usage limiting features to ensure that we don’t incur excessive cost. Implement an API that allows users to see how much token usage they have incurred across the different models they have used.
    1. In addition, implement an admin API for limiting usage. Admins should be able to set limits (short term rate limits, long term rate limits, and/or total limits) which then cause the server to throw errors when the user hits those limits.
3. Specify and implement one bonus feature according to whatever you think the users of this service would find most value in. Here are some ideas, but feel free to add your own.
    - A UI for admins to view/administer usage and billing for all users
    - A UI for users to see the history of calls that they’ve sent with their associated usage
    - A load test to see how well the service responds under millions of QPS
    - Request queueing to avoid overwhelming the service under load
    - Some type of sandboxing to guarantee that user requests are totally isolated and secure
