import openai
import numpy as np
import json
import time
import sys
import os

import google.generativeai as genai
from anthropic import Anthropic

os.environ['NO_PROXY'] = 'localhost,127.0.0.1'

# 自定义模型服务配置
CUSTOM_MODEL_BASE_URL = "http://7.216.57.92:24073/v1"
CUSTOM_MODEL_NAME = "Qwen3-32B"
CUSTOM_EMBEDDING_BASE_URL = "http://7.216.57.92:24067/v1"
CUSTOM_EMBEDDING_API_KEY = "token-abc123"


def get_openai_embedding(texts, model="Qwen3-Embedding-8B"):
    from openai import OpenAI
    client = OpenAI(
        base_url=CUSTOM_EMBEDDING_BASE_URL,
        api_key=CUSTOM_EMBEDDING_API_KEY
    )
    texts = [text.replace("\n", " ") for text in texts]
    embedding = client.embeddings.create(
        model=model,
        input=texts,
        encoding_format='float'
    )
    return np.array([item.embedding for item in embedding.data])

def set_anthropic_key():
    pass

def set_gemini_key():

    # Or use `os.getenv('GOOGLE_API_KEY')` to fetch an environment variable.
    genai.configure(api_key=os.environ['GOOGLE_API_KEY'])

def set_openai_key():
    openai.api_key = os.environ.get('OPENAI_API_KEY', 'token-abc123')


def run_json_trials(query, num_gen=1, num_tokens_request=1000, 
                model='davinci', use_16k=False, temperature=1.0, wait_time=1, examples=None, input=None):

    run_loop = True
    counter = 0
    output = ""
    facts = {}
    while run_loop:
        try:
            if examples is not None and input is not None:
                output = run_chatgpt_with_examples(query, examples, input, num_gen=num_gen, wait_time=wait_time,
                                                   num_tokens_request=num_tokens_request, use_16k=use_16k, temperature=temperature).strip()
            else:
                output = run_chatgpt(query, num_gen=num_gen, wait_time=wait_time, model=model,
                                                   num_tokens_request=num_tokens_request, use_16k=use_16k, temperature=temperature)
            output = output.replace('json', '') # this frequently happens
            facts = json.loads(output.strip())
            run_loop = False
        except json.decoder.JSONDecodeError:
            counter += 1
            time.sleep(1)
            print("Retrying to avoid JsonDecodeError, trial %s ..." % counter)
            print(output)
            if counter == 10:
                print("Exiting after 10 trials")
                sys.exit()
            continue
    return facts


def run_claude(query, max_new_tokens, model_name):

    if model_name == 'claude-sonnet':
        model_name = "claude-3-sonnet-20240229"
    elif model_name == 'claude-haiku':
        model_name = "claude-3-haiku-20240307"

    client = Anthropic(
    # This is the default and can be omitted
    api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )
    # print(query)
    message = client.messages.create(
        max_tokens=max_new_tokens,
        messages=[
            {
                "role": "user",
                "content": query,
            }
        ],
        model=model_name,
    )
    print(message.content)
    return message.content[0].text


def run_gemini(model, content: str, max_tokens: int = 0):

    try:
        response = model.generate_content(content)
        return response.text
    except Exception as e:
        print(f'{type(e).__name__}: {e}')
        return None


def run_chatgpt(query, num_gen=1, num_tokens_request=1000, 
                model='chatgpt', use_16k=False, temperature=1.0, wait_time=1) -> str:

    from openai import OpenAI
    client = OpenAI(
        base_url=CUSTOM_MODEL_BASE_URL,
        api_key=CUSTOM_EMBEDDING_API_KEY
    )

    completion = None
    while completion is None:
        wait_time = wait_time * 2
        try:
            messages = [
                {"role": "user", "content": query}
            ]
            completion = client.chat.completions.create(
                model=CUSTOM_MODEL_NAME,
                temperature=temperature,
                # max_tokens=num_tokens_request,
                n=num_gen,
                messages=messages,
                extra_body={
                    "chat_template_kwargs": {"enable_thinking": False}
                }
            )
        except Exception as e:
            print(f"API Error: {e}; waiting for {wait_time} seconds")
            time.sleep(wait_time)
            pass
    print(completion.choices[0].message.content)
    return completion.choices[0].message.content.replace("```json", "").replace("```", "") if completion.choices[0].message.content else ""
    

    
def run_chatgpt_with_examples(query, examples, input, num_gen=1, num_tokens_request=1000, use_16k=False, wait_time = 1, temperature=1.0):

    from openai import OpenAI
    client = OpenAI(
        base_url=CUSTOM_MODEL_BASE_URL,
        api_key=CUSTOM_EMBEDDING_API_KEY
    )
    
    messages = [
        {"role": "system", "content": query}
    ]
    for inp, out in examples:
        messages.append(
            {"role": "user", "content": inp}
        )
        messages.append(
            {"role": "system", "content": out}
        )
    messages.append(
        {"role": "user", "content": input}
    )   
    
    completion = None
    while completion is None:
        wait_time = wait_time * 2
        try:
            completion = client.chat.completions.create(
                model=CUSTOM_MODEL_NAME,
                temperature=temperature,
                # max_tokens=num_tokens_request,
                n=num_gen,
                messages=messages,
                extra_body={
                    "chat_template_kwargs": {"enable_thinking": False}
                }
            )
        except Exception as e:
            print(f"API Error: {e}; waiting for {wait_time} seconds")
            time.sleep(wait_time)
            pass
    
    return completion.choices[0].message.content.replace("```json", "").replace("```", "") if completion.choices[0].message.content else ""
