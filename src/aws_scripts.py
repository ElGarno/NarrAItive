import psycopg2
from datetime import datetime
from creds_db import DBConfig
from creds_aws import AWSConfig
import streamlit as st
import boto3


REGION = "eu-central-1"


def initialize_s3_client(aws_access_key, aws_secret_key):
    # Initialize the S3 client
    s3_client = boto3.client('s3', region_name=REGION,
                             aws_access_key_id=aws_access_key,
                             aws_secret_access_key=aws_secret_key)
    return s3_client


def prepare_aws_environment():
    client = initialize_s3_client(AWSConfig.AWS_ACCESS_KEY, AWSConfig.AWS_SECRET_KEY)
    # Ensure the table exists
    return client


def upload_image_to_s3(s3_cl, bucket_name, file_path, story_id, image_id):
    """Upload an image to S3 and return its URL."""
    object_name = f"{story_id}/{image_id}.jpg"
    s3_cl.upload_file(file_path, bucket_name, object_name)
    # Construct the S3 URL
    url = f"https://{bucket_name}.s3.amazonaws.com/{object_name}"
    return url


def upload_audio_to_s3(s3_cl, bucket_name, file_path, story_id, audio_id):
    """Upload an audio file to S3 and return its URL."""
    object_name = f"{story_id}/{audio_id}.mp3"
    s3_cl.upload_file(file_path, bucket_name, object_name)
    # Construct the S3 URL
    url = f"https://{bucket_name}.s3.amazonaws.com/{object_name}"
    return url


def delete_s3_objects(s3_cl, bucket_name, prefix):
    response = s3_cl.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

    if 'Contents' in response:
        delete_keys = {'Objects': [{'Key': obj['Key']} for obj in response['Contents']]}
        s3_cl.delete_objects(Bucket=bucket_name, Delete=delete_keys)

    # log how many objects were deleted
    if 'KeyCount' in response:
        st.info(f"Deleted {response['KeyCount']} objects from S3")


def download_image(s3_cl, bucket_name, story_id, image_id, local_file_path):
    # Download the image from S3 and save it to the local file system
    object_name = f"{story_id}/{image_id}.jpg"
    s3_cl.download_file(bucket_name, object_name, local_file_path)


def download_audio(s3_cl, bucket_name, story_id, audio_id, local_file_path):
    # Download the image from S3 and save it to the local file system
    object_name = f"{story_id}/{audio_id}.mp3"
    s3_cl.download_file(bucket_name, object_name, local_file_path)


def save_avatar_img_locally(file_path, uploaded_file):
    # To read file as bytes:
    bytes_data = uploaded_file.getvalue()

    # To save the file, you can write it to a location
    with open(file_path, "wb") as f:
        f.write(bytes_data)
    st.success('File saved successfully!')


def delete_story(story_id):
    with connect_to_db() as conn:
        with conn.cursor() as cursor:
            try:
                # Just delete the story, and cascading will take care of the rest
                # Delete operations
                cursor.execute("DELETE FROM audios WHERE segment_id IN (SELECT segment_id FROM story_segments WHERE story_id = %s)", (story_id,))
                cursor.execute("DELETE FROM images WHERE segment_id IN (SELECT segment_id FROM story_segments WHERE story_id = %s)", (story_id,))
                cursor.execute("DELETE FROM story_segments WHERE story_id = %s", (story_id,))
                cursor.execute("DELETE FROM story WHERE story_id = %s", (story_id,))
                # Commit the transaction
                conn.commit()
            except Exception as e:
                print(f"An error occurred: {e}")
                conn.rollback()  # Rollback in case of any error


def get_stories():
    with connect_to_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT story_id, title FROM story ORDER BY creation_timestamp DESC")
            stories = cursor.fetchall()
    return stories


@st.cache_data
def get_story_segments_and_image_urls(story_id):
    with connect_to_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT ss.segment_id, ss.content, i.url, i.image_id, aud.url, aud.audio_id
                FROM story_segments ss
                LEFT JOIN images i ON ss.segment_id = i.segment_id
                LEFT JOIN audios aud ON ss.segment_id = aud.segment_id
                WHERE ss.story_id = %s
                ORDER BY ss.segment_pos
            """, (story_id,))
            segments = cursor.fetchall()
    return segments


@st.cache_resource
def connect_to_db():
    return psycopg2.connect(
        dbname=DBConfig.DB_NAME,
        user=DBConfig.DB_USER,
        password=DBConfig.DB_PASSWORD,
        host=DBConfig.DB_HOST,
        port=DBConfig.DB_PORT
    )


def store_image_metadata(url, image_id, segment_id, model, resolution):
    creation_time = datetime.now()
    with connect_to_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO images (image_id, segment_id, url, creation_timestamp, creation_model, resolution) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (image_id, segment_id, url, creation_time, model, resolution))
            conn.commit()


def store_segment_metadata(story_id, segment_id, segment_pos, content, image_prompt):
    with connect_to_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO story_segments (story_id, segment_id, segment_pos, content, image_prompt) 
                VALUES (%s, %s, %s, %s, %s)
            """, (story_id, segment_id, segment_pos, content, image_prompt))
            conn.commit()


def store_story_metadata(story_id, num_segments, title, age, llm):
    creation_time = datetime.now()
    with connect_to_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO story (story_id, num_segments, title, age, llm, creation_timestamp) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (story_id, num_segments, title, age, llm, creation_time))
            conn.commit()


def store_audio_metadata(url, audio_id, segment_id, model, voice):
    creation_time = datetime.now()
    with connect_to_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO audios (audio_id, segment_id, url, creation_timestamp, creation_model, voice) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (audio_id, segment_id, url, creation_time, model, voice))
            conn.commit()
