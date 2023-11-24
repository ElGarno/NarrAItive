import requests
import boto3
import base64
import openai


def get_completion_from_messages(api_key,
                                 messages,
                                 model="gpt-3.5-turbo-16k",
                                 temperature=0,
                                 max_tokens=3500):
    client = openai.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


def get_audio_from_text_and_save_to_file(api_key,
                                         text,
                                         speech_file_path,
                                         model="tts-1",
                                         voice="alloy"):
    client = openai.OpenAI(api_key=api_key)
    response = client.audio.speech.create(
        model=model,
        voice="alloy",
        input=text
    )
    response.stream_to_file(speech_file_path)


def get_image_from_prompt(api_key,
                          prompt,
                          model="dall-e-3"):
    client = openai.OpenAI(api_key=api_key)
    response = client.images.generate(
        prompt=prompt,
        model=model,  # Use the DALL-E model
        n=1,
        size="1024x1024"
    )
    image_url = response.data[0].url
    return image_url


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def get_description_from_image(api_key,
                               image_url,
                               model="gpt-4-vision-preview"):
    # Path to your image
    image_path = image_url

    # Getting the base64 string
    base64_image = encode_image(image_path)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Please describe the character in this image in about 2 sentences and don't talk about"
                                " the image itself. Just describe the character and start with "
                                "'A toddler, A boy.. / a girl / a man...' Make sure that you describe the colour of "
                                "hair and the potential age of the character."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 300
    }
    response = None
    for i_try in range(10):
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        if response.status_code == 200:
            break
    return response.json()["choices"][0]['message']['content']