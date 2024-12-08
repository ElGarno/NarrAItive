import psycopg2
from datetime import datetime
from creds_db import DBConfig
from creds_aws import AWSConfig
import streamlit as st
import duckdb
import boto3
import json
import os

# Add at top with other constants
REGION = "eu-central-1"
DB_PATH = 'narrAItive_duckDB.duckdb'

# Global connection pool
_db_connection = None

def get_db_connection():
    """Get or create database connection"""
    global _db_connection
    if (_db_connection is None):
        _db_connection = duckdb.connect(DB_PATH)
    return _db_connection

def close_db_connection():
    """Close the database connection"""
    global _db_connection
    if _db_connection:
        _db_connection.close()
        _db_connection = None

def execute_query(query, params=None, fetch=True):
    """Execute a query and optionally fetch results"""
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute(query, params or ())
        if fetch:
            return cursor.fetchall()
        conn.commit()

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


def upload_file_to_s3(s3_cl, file, bucket_name, object_name):
    try:
        s3_cl.upload_file(file, bucket_name, object_name)
        # Construct the S3 URL
        url = f"https://{bucket_name}.s3.amazonaws.com/{object_name}"
        return url
    except Exception as e:
        st.error(f"An error occurred: {e}")
        return False


def save_file_locally(uploaded_file, save_path):
    # Create the directory if it doesn't exist
    if not os.path.exists(save_path):
        os.makedirs(save_path)

    # Define the full file path
    file_path = os.path.join(save_path, uploaded_file.name)

    # Write the file to the specified directory
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    return file_path


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


def delete_single_objects_from_s3(s3_cl, bucket_name, object_name):
    try:
        s3_cl.delete_object(Bucket=bucket_name, Key=object_name)
        st.info(f"Deleted {object_name} from S3")
        return True
    except Exception as e:
        st.error(f"An error occurred: {e}")
        return False


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
    try:
        queries = [
            "DELETE FROM audios WHERE segment_id IN (SELECT segment_id FROM story_segments WHERE story_id = ?)",
            "DELETE FROM images WHERE segment_id IN (SELECT segment_id FROM story_segments WHERE story_id = ?)",
            "DELETE FROM story_segments WHERE story_id = ?",
            "DELETE FROM story WHERE story_id = ?"
        ]
        
        conn = get_db_connection()
        with conn.cursor() as cursor:
            for query in queries:
                cursor.execute(query, (story_id,))
            conn.commit()
    except Exception as e:
        print(f"An error occurred: {e}")
        conn.rollback()


def get_stories():
    return execute_query("SELECT story_id, title FROM story ORDER BY creation_timestamp DESC")


# @st.cache_data
def get_story_segments_and_image_urls(story_id):
    return execute_query("""
        SELECT ss.segment_id, ss.content, i.url, i.image_id, aud.url, aud.audio_id, ss.image_prompt, aud.voice
        FROM story_segments ss
        LEFT JOIN images i ON ss.segment_id = i.segment_id
        LEFT JOIN audios aud ON ss.segment_id = aud.segment_id
        WHERE ss.story_id = ?
        ORDER BY ss.segment_pos
    """, (story_id,))


def check_voice_exists_for_story(story_id, voice_id):
    result = execute_query("""
        SELECT EXISTS(
            SELECT 1 FROM audios a
            JOIN story_segments ss ON a.segment_id = ss.segment_id
            WHERE ss.story_id = ? AND a.voice = ?
        )
    """, (story_id, voice_id))
    return result[0][0]


def get_audio_id_by_segment_and_voice(segment_id, cur_voice):
    result = execute_query("""
        SELECT audio_id FROM audios
        WHERE segment_id = ? AND voice = ?
    """, (segment_id, cur_voice))
    return result[0][0]


@st.cache_resource
def connect_to_db():
    return psycopg2.connect(
        dbname=DBConfig.DB_NAME,
        user=DBConfig.DB_USER,
        password=DBConfig.DB_PASSWORD,
        host=DBConfig.DB_HOST,
        port=DBConfig.DB_PORT
    )


def connect_to_duckdb():
    return duckdb.connect('narrAItive_duckDB.duckdb')


def store_image_metadata(url, image_id, segment_id, model, resolution):
    creation_time = datetime.now()
    execute_query(
        """INSERT INTO images (image_id, segment_id, url, creation_timestamp, creation_model, resolution) 
           VALUES (?, ?, ?, ?, ?, ?)""",
        (image_id, segment_id, url, creation_time, model, resolution),
        fetch=False
    )


def store_segment_metadata(story_id, segment_id, segment_pos, content, image_prompt):
    execute_query(
        """INSERT INTO story_segments (story_id, segment_id, segment_pos, content, image_prompt) 
           VALUES (?, ?, ?, ?, ?)""",
        (story_id, segment_id, segment_pos, content, image_prompt),
        fetch=False
    )


def store_story_metadata(story_id, num_segments, title, age, llm):
    creation_time = datetime.now()
    execute_query(
        """INSERT INTO story (story_id, num_segments, title, age, llm, creation_timestamp) 
           VALUES (?, ?, ?, ?, ?, ?)""",
        (story_id, num_segments, title, age, llm, creation_time),
        fetch=False
    )


def store_audio_metadata(url, audio_id, segment_id, model, voice):
    creation_time = datetime.now()
    execute_query(
        """INSERT INTO audios (audio_id, segment_id, url, creation_timestamp, creation_model, voice) 
           VALUES (?, ?, ?, ?, ?, ?)""",
        (audio_id, segment_id, url, creation_time, model, voice),
        fetch=False
    )


def store_voice_metadata(name, voice_id, category, training_files, labels):
    creation_time = datetime.now()
    execute_query(
        """INSERT INTO voices (name, voice_id, category, training_files, labels, creation_datetime) 
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, voice_id, category, training_files, json.dumps(labels), creation_time),
        fetch=False
    )


def get_voice_id_by_voice_name(voice_name):
    result = execute_query("""
        SELECT voice_id FROM voices WHERE name = ?
    """, (voice_name,))
    return result[0][0]


def get_all_voice_categories():
    result = execute_query("""
        SELECT DISTINCT category FROM voices
    """)
    return [row[0] for row in result]


def get_all_accents_from_labels():
    return execute_query("""
        SELECT DISTINCT labels->>'accent' FROM voices
    """)


def get_all_ages_from_labels():
    return execute_query("""
        SELECT DISTINCT labels->>'age' FROM voices
    """)


def get_all_genders_from_labels():
    return execute_query("""
        SELECT DISTINCT labels->>'gender' FROM voices
    """)


def get_all_use_cases_from_labels():
    return execute_query("""
        SELECT DISTINCT labels->>'use_case' FROM voices
    """)


def get_all_voices_for_category(category):
    return execute_query("""
        SELECT voice_id, name, labels FROM voices WHERE category = ?
    """, (category,))


def delete_image_record(image_id):
    try:
        execute_query("""
            DELETE FROM images WHERE image_id = ?
        """, (image_id,), fetch=False)
    except Exception as e:
        print(f"An error occurred: {e}")


# Add cleanup function to be called when application shuts down
def cleanup():
    close_db_connection()
