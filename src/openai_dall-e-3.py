# Bring in deps
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
                         download_audio, delete_s3_objects, delete_story)
from aws_scripts import prepare_aws_environment
from story_creating_utils import check_characters, generate_dall_e_3_gpt_dict
from process_media import process_image, process_audio, process_audio_wrapper, process_image_wrapper

# Define constants
BUCKET_NAME = "narraitive"

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
    if 'dict_dall_e_3_gpt' not in st.session_state:
        st.session_state.dict_dall_e_3_gpt = {}
    if 'dict_characters' not in st.session_state:
        st.session_state.dict_characters = {}
    if 'dict_openai_api_costs' not in st.session_state:
        st.session_state.dict_openai_api_costs = {}

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
        segments = get_story_segments_and_image_urls(story_selectbox[0])
        # print(segments)
        st.session_state.stage = 2
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
            download_image(s3_client, BUCKET_NAME, story_selectbox[0], st.session_state.dict_dall_e_3_gpt["segments"][i_segment]["image_id"], loc_file_path)
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
        openai.api_key = openai_api_key
        topic = st.text_input("What should the story be about?", placeholder="Story topic")
        # get the age from a streamlit selectbox widget
        children_age = st.selectbox("What is the age of the children?", ["1-2", "3-5", "6-8", "9-11"])
        templates_prompt = prompt_templates(topic, children_age)
        parallel_execution = st.sidebar.checkbox("Create images and audio in parallel", False, key="parallel")
        # streamlit widget to save the settings and start generating the story
        st.button("Generate Story", on_click=set_stage, args=(1,))
        if st.session_state.stage == 1:
            # generate story uuid
            story_id = str(uuid.uuid4())
            # generate characters
            (st.session_state.dict_characters, st.session_state.message_list,
             description_generated) = check_characters(templates_prompt, openai_api_key, st.session_state.message_list)
            st.session_state.dict_openai_api_costs["check_characters"] = f"{0:.3f}$"

            if description_generated:
                st.session_state.stage = 2
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
                            process_audio(openai_api_key, segment_content, i_seg, story_id, segment_id, s3_client, bucket_name=BUCKET_NAME)
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

    if st.session_state.stage > 1:
        # get number of segments
        number_segments = len(st.session_state.dict_dall_e_3_gpt["segments"])
        if streamlit.checkbox("Show all messages"):
            st.write(st.session_state.message_list)

        # set index = 0 only for the first run
        if "index" not in st.session_state:
            st.session_state.index = 0
        # Adding text to images and displaying them
        # Create buttons for next and previous
        if st.button('Previous', on_click=set_stage, args=(2,)):
            st.session_state.index = (st.session_state.index - 1) % number_segments

        if st.button('Next', on_click=set_stage, args=(2,)):
            st.session_state.index = (st.session_state.index + 1) % number_segments
        st.write(st.session_state.dict_dall_e_3_gpt["segments"][st.session_state.index]["content"])

        # Open the image, add text and display it
        img_path = st.session_state.dict_dall_e_3_gpt["segments"][st.session_state.index]["image_path"]
        with Image.open(img_path) as img:
            st.image(img, width=800)
            # Display the caption with customized font size
            # st.markdown(f'<p style="font-size:38px">{texts[st.session_state["index"]]}</p>', unsafe_allow_html=True)
        # Display the audio
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
