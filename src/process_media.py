import uuid
from aws_scripts import upload_image_to_s3, upload_audio_to_s3, store_image_metadata, store_audio_metadata
from ai_model_apis import get_image_from_prompt, get_audio_from_text_and_save_to_file
import requests


def process_image(openai_api_key, image_prompt, i_seg, story_id, segment_id, s3_client, bucket_name):
    image_url = get_image_from_prompt(api_key=openai_api_key, prompt=image_prompt)
    # write image to local file
    write_image_from_url_to_file(image_url, "img", f"output_{i_seg}")
    # generate image uuid
    image_id = str(uuid.uuid4())
    # write image to aws s3 bucket
    aws_url = upload_image_to_s3(s3_client, bucket_name, f"img/output_{i_seg}.png", story_id, image_id)
    # store image metadata in postgresql
    store_image_metadata(aws_url, image_id, segment_id, "dall_e_3_gpt", "1024x1024")


def process_audio(openai_api_key, segment_content, i_seg, story_id, segment_id, s3_client, bucket_name):
    get_audio_from_text_and_save_to_file(api_key=openai_api_key,
                                         text=segment_content,
                                         speech_file_path=f"audio/output_{i_seg}.mp3",
                                         model="tts-1",
                                         voice="alloy")
    audio_id = str(uuid.uuid4())
    # upload audio to aws s3 bucket
    aws_audio_url = upload_audio_to_s3(s3_cl=s3_client, bucket_name=bucket_name, file_path=f"audio/output_{i_seg}.mp3", story_id=story_id, audio_id=audio_id)
    # store audio metadata in postgresql
    store_audio_metadata(url=aws_audio_url, audio_id=audio_id, segment_id=segment_id, model="tts-1", voice="alloy")


def write_image_from_url_to_file(url, file_path, image_id):
    img_data = requests.get(url).content
    with open(f'{file_path}/{image_id}.png', 'wb') as f:
        f.write(img_data)


# Function to wrap process_image for ThreadPoolExecutor
def process_image_wrapper(args):
    return process_image(**args)


# Function to wrap process_audio for ThreadPoolExecutor
def process_audio_wrapper(args):
    return process_audio(**args)