# Bring in deps
import os
import json
import streamlit
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import openai
import uuid
from pydub import AudioSegment
from concurrent.futures import ThreadPoolExecutor
from prompt_templates import prompt_templates
from aws_scripts import (store_story_metadata, store_segment_metadata,
                         get_stories, get_story_segments_and_image_urls, download_image,
                         download_audio, delete_s3_objects, delete_story, upload_file_to_s3, save_file_locally)
from aws_scripts import prepare_aws_environment, get_all_voices_for_category, get_all_voice_categories, store_voice_metadata
from story_creating_utils import check_characters, generate_dall_e_3_gpt_dict
from process_media import process_image, process_audio, process_audio_wrapper, process_image_wrapper
from ai_model_apis import clone_voice

# Define constants
BUCKET_NAME = "narraitive"
# test

# Customize the layout
st.set_page_config(page_title="Dall-E-3 GPT", page_icon="🤖", layout="wide", )

# st.markdown(f"""
#             <style>
#             .stApp {{background-image: url("https://cdn.pixabay.com/photo/2015/12/19/20/32/love-1100256_1280.jpg");
#                      background-attachment: fixed;
#                      background-size: cover}}
#          </style>
#          """, unsafe_allow_html=True)


def set_stage(stage):
    st.session_state.stage = stage


def main():
    openai_api_key = st.sidebar.text_input('OpenAI API Key')
    # fetch credentials
    s3_client = prepare_aws_environment()
    st.title("NarrAItive 🤖")
    st.sidebar.header("History")
    if 'stage' not in st.session_state:
        st.session_state.stage = 0
    if 'message_list' not in st.session_state:
        st.session_state.message_list = []
    if 'voice_inputs' not in st.session_state:
        st.session_state.voice_inputs = []
    if 'dict_dall_e_3_gpt' not in st.session_state:
        st.session_state.dict_dall_e_3_gpt = {}
    if 'dict_characters' not in st.session_state:
        st.session_state.dict_characters = {}
    if 'dict_openai_api_costs' not in st.session_state:
        st.session_state.dict_openai_api_costs = {}
    if 'story_id' not in st.session_state:
        st.session_state.story_id = ""

    # stories[0] = story_id, stories[1] = story_title
    stories = get_stories()
    story_selectbox = st.sidebar.selectbox(
        'Select a story',
        stories,
        format_func=lambda x: x[1]
    )
    apply_button = st.sidebar.button('Load Story')
    delete_button = st.sidebar.button('Delete Story')
    if apply_button:
        st.session_state.story_id = story_selectbox[0]
        segments = get_story_segments_and_image_urls(st.session_state.story_id)
        # print(segments)
        st.session_state.stage = 3
        # fill dict with segments
        st.session_state.dict_dall_e_3_gpt["title"] = story_selectbox[1]
        st.session_state.dict_dall_e_3_gpt["segments"] = []
        for segment_id, content, image_url, image_id, audio_url, audio_id in segments:
            st.session_state.dict_dall_e_3_gpt["segments"].append({
                "segment_id": segment_id,
                "content": content,
                "image_path": image_url,
                "image_id": image_id,
                "audio_path": audio_url,
                "audio_id": audio_id
            })
        for i_segment in range(len(st.session_state.dict_dall_e_3_gpt["segments"])):
            loc_file_path = f"img/output_{i_segment}.png"
            download_image(s3_client, BUCKET_NAME, st.session_state.story_id, st.session_state.dict_dall_e_3_gpt["segments"][i_segment]["image_id"], loc_file_path)
            st.session_state.dict_dall_e_3_gpt["segments"][i_segment]["image_path"] = f"img/output_{i_segment}.png"
            loc_file_path_audio = f"audio/output_{i_segment}.mp3"
            download_audio(s3_client, BUCKET_NAME, story_selectbox[0], st.session_state.dict_dall_e_3_gpt["segments"][i_segment]["audio_id"], loc_file_path_audio)
            st.session_state.dict_dall_e_3_gpt["segments"][i_segment]["audio_path"] = f"audio/output_{i_segment}.mp3"
    if delete_button:
        delete_s3_objects(s3_client, BUCKET_NAME, story_selectbox[0])
        delete_story(story_selectbox[0])

    if not openai_api_key.startswith('sk-'):
        st.warning('Please enter your OpenAI API key!', icon='⚠')
    else:
        st.success('API key is valid ✅')
        elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
        openai.api_key = openai_api_key
        topic = st.text_input("What should the story be about?", placeholder="Story topic")
        # get the age from a streamlit selectbox widget
        children_age = st.selectbox("What is the age of the children?", ["1-2", "3-5", "6-8", "9-11"])
        # get the voice from a streamlit selectbox widget
        voice_category = st.selectbox("What is the voice category?", get_all_voice_categories())
        voices = get_all_voices_for_category(voice_category)
        selected_voice = st.selectbox("What is the voice?", voices)
        # only take the id of the voice, so the first value of selected_voice
        selected_voice = selected_voice[0]
        local_voice_save_path = "voice_input"
        local_voice_file_paths = []
        cloud_voice_file_paths = []
        if st.button("Clone own voice!"):
            st.session_state.stage = 1
        if st.session_state.stage == 1:
            st.session_state.voice_inputs = st.file_uploader("Upload at least 5 voice samples!", type=['m4a'], accept_multiple_files=True)
            if st.session_state.voice_inputs:
                for uploaded_file in st.session_state.voice_inputs:
                    local_voice_file_path = save_file_locally(uploaded_file, local_voice_save_path)
                    st.write(f"Saved locally at: {local_voice_file_path}")
                    local_voice_file_paths.append(local_voice_file_path)
                    # Define the S3 object name (key)
                    s3_object_name = f"voices/{uploaded_file.name}"
                    # Upload the file
                    voice_url = upload_file_to_s3(s3_client, local_voice_file_path, BUCKET_NAME, s3_object_name)
                    cloud_voice_file_paths.append(voice_url)
                # input fields for name, description and labels: (age, accent, gender, use_case, description)
                # Using Streamlit's form feature to group inputs together
                with st.form(key='voice_form'):
                    inp_voice_name = st.text_input("Name of the voice", "My voice")
                    inp_voice_descr = st.text_input("Description of the voice", "Description here like 'calm, friendly, ...'")
                    try:
                        inp_voice_labels = json.loads(st.text_input("Enter labels", '{"age": "young", "accent": "german", "gender": "male", "use-case": "narration"}'))
                    except json.JSONDecodeError:
                        st.error("Labels must be in valid JSON format.")
                        inp_voice_labels = {}

                    submit_button = st.form_submit_button("Confirm")

                # Check if the form is submitted and all fields are filled out
                if submit_button:
                    if inp_voice_name != "My voice" and inp_voice_descr != "Description here like 'calm, friendly, ...'" and inp_voice_labels:
                        # Proceed with processing the data
                        st.success("Form submitted successfully!")
                        # You can add your logic here to handle the form data
                        cloned_voice = clone_voice(elevenlabs_api_key, local_voice_file_paths, inp_voice_name, inp_voice_descr, inp_voice_labels)
                        store_voice_metadata(cloned_voice.name, cloned_voice.voice_id, cloned_voice.category, cloud_voice_file_paths, cloned_voice.labels)
                        selected_voice = cloned_voice.name
                    else:
                        # Show an error message
                        st.warning("Please fill out all fields with valid information.")
        templates_prompt = prompt_templates(topic, children_age)
        parallel_execution = st.sidebar.checkbox("Create images and audio in parallel", False, key="parallel")
        # streamlit widget to save the settings and start generating the story
        st.button("Generate Story", on_click=set_stage, args=(2,))
        if st.session_state.stage == 2:
            # generate story uuid
            story_id = str(uuid.uuid4())
            # generate characters
            (st.session_state.dict_characters, st.session_state.message_list,
             description_generated) = check_characters(templates_prompt, openai_api_key, st.session_state.message_list)
            st.session_state.dict_openai_api_costs["check_characters"] = f"{0:.3f}$"

            if description_generated:
                st.session_state.stage = 3
                with st.spinner("Generating story..."):
                    st.session_state.dict_dall_e_3_gpt, st.session_state.message_list = generate_dall_e_3_gpt_dict(
                        templates_prompt,
                        openai_api_key,
                        st.session_state.message_list,
                        st.session_state.dict_characters
                    )
                    st.session_state.dict_openai_api_costs["generate_dall_e_3_gpt_dict"] = f"{0:.3f}$"
                # extract story title
                story_title = st.session_state.dict_dall_e_3_gpt["title"]
                st.write(st.session_state.dict_dall_e_3_gpt)
                # get number of segments
                number_segments = len(st.session_state.dict_dall_e_3_gpt["segments"])
                # store story metadata in postgresql
                store_story_metadata(story_id, number_segments, story_title, children_age, "gpt-3.5-turbo-16k")
                # generate image for each segment and store image in folder "img"
                # list for process image args
                if parallel_execution:
                    process_image_args = []
                    process_audio_args = []
                if not parallel_execution:
                    progress_text = f"Generating images and audio for the picture-book. Please wait..."
                    my_progress_bar = st.progress(0, text=progress_text)
                    api_image_costs = 0
                    api_audio_costs = 0
                for i_seg in range(number_segments):
                    if not parallel_execution:
                        my_progress_bar.progress(i_seg / number_segments, text=progress_text)
                    # get image prompt
                    image_prompt = st.session_state.dict_dall_e_3_gpt["segments"][i_seg]["image_prompt"]
                    segment_content = st.session_state.dict_dall_e_3_gpt["segments"][i_seg]["content"]
                    # generate segment uuid
                    segment_id = str(uuid.uuid4())
                    # store segment metadata in postgresql
                    store_segment_metadata(story_id, segment_id, i_seg, segment_content, image_prompt)
                    # preparations for parallel image generation
                    if parallel_execution:
                        process_image_args.append({'openai_api_key': openai_api_key, 'image_prompt': image_prompt, 'i_seg': i_seg, 'story_id': story_id, 'segment_id': segment_id, 's3_client': s3_client, 'bucket_name': BUCKET_NAME})
                    else:
                        with st.spinner("Generating image..."):
                            process_image(openai_api_key, image_prompt, i_seg, story_id, segment_id, s3_client, bucket_name=BUCKET_NAME)
                            api_image_costs += 0.0
                    # append image path to dict
                    st.session_state.dict_dall_e_3_gpt["segments"][i_seg]["image_path"] = f"img/output_{i_seg}.png"
                    # preparation for parallel audio generation
                    if parallel_execution:
                        process_audio_args.append({'openai_api_key': openai_api_key, 'segment_content': segment_content, 'i_seg': i_seg, 'story_id': story_id, 'segment_id': segment_id, 's3_client': s3_client})
                    else:
                        with st.spinner("Generating audio..."):
                            process_audio(elevenlabs_api_key, segment_content, i_seg, story_id, segment_id, s3_client, bucket_name=BUCKET_NAME, model="eleven_multilingual_v2", voice=selected_voice)
                            api_audio_costs += 0.0
                    # append audio path to dict
                    st.session_state.dict_dall_e_3_gpt["segments"][i_seg]["audio_path"] = f"audio/output_{i_seg}.mp3"
                if not parallel_execution:
                    my_progress_bar.progress(1.0, text="Done!")
                    st.success("Images and audio successfully generated!")
                    st.session_state.dict_openai_api_costs["generate_images"] = f"{api_image_costs:.3f}$"
                    st.session_state.dict_openai_api_costs["generate_audio"] = f"{api_audio_costs:.3f}$"
                if parallel_execution:
                    # generate images and audio in parallel
                    with st.spinner("Generating image..."):
                        with ThreadPoolExecutor(max_workers=10) as executor:
                            executor.map(process_image_wrapper, process_image_args)
                    with st.spinner("Generating audio..."):
                        with ThreadPoolExecutor(max_workers=10) as executor:
                            executor.map(process_audio_wrapper, process_audio_args)

    if st.session_state.stage > 2:
        # get number of segments
        number_segments = len(st.session_state.dict_dall_e_3_gpt["segments"])
        if streamlit.checkbox("Show all messages"):
            st.write(st.session_state.message_list)

        # set index = 0 only for the first run
        if "index" not in st.session_state:
            st.session_state.index = 0
        # Adding text to images and displaying them
        # Create buttons for next and previous
        if st.button('Previous', on_click=set_stage, args=(3,)):
            st.session_state.index = (st.session_state.index - 1) % number_segments

        if st.button('Next', on_click=set_stage, args=(3,)):
            st.session_state.index = (st.session_state.index + 1) % number_segments
        st.write(st.session_state.dict_dall_e_3_gpt["segments"][st.session_state.index]["content"])

        # Open the image, add text and display it
        img_path = st.session_state.dict_dall_e_3_gpt["segments"][st.session_state.index]["image_path"]
        with Image.open(img_path) as img:
            st.image(img, width=800)
            # Display the caption with customized font size
            # st.markdown(f'<p style="font-size:38px">{texts[st.session_state["index"]]}</p>', unsafe_allow_html=True)
        # Display the audio
        if st.button("Regenerate image"):
            with st.spinner("Regenerating image..."):
                image_prompt = st.session_state.dict_dall_e_3_gpt["segments"][st.session_state.index]["image_prompt"]
                i_seg = st.session_state.index
                story_id = story_selectbox[0]
                segment_id = st.session_state.dict_dall_e_3_gpt["segments"][st.session_state.index]["segment_id"]
                image_id = st.session_state.dict_dall_e_3_gpt["segments"][st.session_state.index]["image_id"]
                process_image(openai_api_key, image_prompt, i_seg, story_id, segment_id, s3_client,
                              bucket_name=BUCKET_NAME, replace_old_image=True,
                              replace_image_id=image_id)
        audio_path = st.session_state.dict_dall_e_3_gpt["segments"][st.session_state.index]["audio_path"]
        audio_file = AudioSegment.from_mp3(audio_path)
        audio_file.export("audio/output.wav", format="wav")
        st.audio("audio/output.wav", format="audio/wav")
        if st.sidebar.checkbox("Show costs for API use"):
            if st.session_state.dict_openai_api_costs:
                st.sidebar.write(st.session_state.dict_openai_api_costs)
            else:
                st.sidebar.write("No API calls yet.")


if __name__ == "__main__":
    main()
