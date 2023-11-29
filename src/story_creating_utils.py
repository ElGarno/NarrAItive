from ai_model_apis import get_completion_from_messages, get_description_from_image
from aws_scripts import save_avatar_img_locally
import json
import streamlit as st


def check_characters(templates_prompt, openapi_key, messages):
    messages.append({'role': 'system', 'content': templates_prompt["story"]["system_message_1"]})
    messages.append({'role': 'user', 'content': templates_prompt["story"]["user_message_1"]})
    response = get_completion_from_messages(api_key=openapi_key, messages=messages)
    messages.append({'role': 'assistant', 'content': response})
    dict_characters_response = json.loads(response)
    uploaded_image_character = {}
    for i_character in range(len(dict_characters_response["characters"])):
        character_name = dict_characters_response["characters"][i_character]["name"]
        character_known_by_you = dict_characters_response["characters"][i_character]["known_by_you"]
        if character_known_by_you == "no":
            # user can choose whether he wants to describe the character via text or image
            describe_via_image = st.sidebar.toggle(f'Describe character {character_name} via image?', False, key=f"toggler_{i_character}")
            dict_characters_response["characters"][i_character]["description"] = ""
            if describe_via_image:
                uploaded_image_character[character_name] = st.file_uploader(f"Please upload an image of {character_name}.", type=['jpg', 'jpeg', 'png'], key=f"image_uploader_{i_character}")
                if uploaded_image_character[character_name] is not None:
                    save_avatar_img_locally(f"img/{character_name}.png", uploaded_image_character[character_name])
                    dict_characters_response["characters"][i_character]["description"] = get_description_from_image(openapi_key, f"img/{character_name}.png", model="gpt-4-vision-preview")
                    # print(dict_characters_response["characters"][i_character]["description"])
            else:
                dict_characters_response["characters"][i_character]["description"] = st.text_input(
                    f"Please describe the character {character_name} in more detail.")
            if dict_characters_response["characters"][i_character]["description"] != "":
                dict_characters_response["characters"][i_character]["known_by_you"] = "yes"
    # only return if all characters are known by you
    if all(character["known_by_you"] == "yes" for character in dict_characters_response["characters"]):
        return dict_characters_response, messages, True
    else:
        return dict_characters_response, messages, False


@st.cache_data()
def generate_dall_e_3_gpt_dict(templates_prompt, openai_api_key, messages, dict_characters):
    # append system and user message
    messages.append({'role': 'system', 'content': templates_prompt["story"]["system_message_2"]})
    messages.append({'role': 'user', 'content': templates_prompt["story"]["user_message_2"]})
    response = get_completion_from_messages(api_key=openai_api_key, messages=messages)
    messages.append({'role': 'assistant', 'content': response})
    dict_story_response = json.loads(response)
    # st.write(json.loads(dict_story_response))
    number_segments = len(dict_story_response["segments"])
    # iterate over segments and generate images
    for i_seg in range(number_segments):
        # use content of segment for user message
        segment_content = dict_story_response["segments"][i_seg]["content"]
        # image_template_user_message = f"""Based on the following segment-content you will now generate an image that
        #     fits the story. Here is a dall_e_3 Prompt Formula:
        #     [image we're prompting in about fifteen (15) words], [5 descriptive keywords], [time of day],
        #      [style of photograph]
        #     -- Examples --
        #     1. Group of animated and diverse animals gathered under a twinkling starlit sky, looking curious and
        #     determined, dawn, 3D-animated image in the style of Pixar
        #     2. Star Sniffers approaching a donut-shaped planet with quirky and inviting features, surrounded by a vast
        #     and mysterious cosmos, noon, 3D-animated image in the style of Pixar
        #     --------------
        #     Please transform the following segment (starting with ###) in a dall_e_3 Prompt in the way I described in
        #     the given formula using english language and remove the brackets.
        #     Don't use citations of the segment in the prompt but instead make a description of the situation for the
        #     (image we're prompting) in about ten to fifteen words.
        #     As style it is very important that you use a "3D-animated image in the style of Pixar".
        #     Just return the dall_e_3 Prompt Formula and nothing else! Make sure that you don't repeat or translate the
        #     following segment-contet in the prompt. This is very important!
        #     ###
        #     {segment_content}
        # """
        image_template_user_message = f"""Every chapter should be accompanied by an image which describes the situation.
            Please create the images in a consistent manner so that the style is always "3D animated, Pixar Style"
            and the characters look identical in each image. Pay attention to the colour of hair and the clothes.. 
            -- Examples --
             "A 3D animated Pixar-style image of a young blonde girl named Emilia, standing in front of a small, 
             cozy village house. She looks excited, wearing a bright red jacket and blue jeans, with a small backpack. 
             She has big, curious eyes and a wide, eager smile. Her blonde hair is tied in two ponytails."

             "A 3D animated Pixar-style image of Emilia, the young blonde girl, exploring Times Square in New York. 
             She's looking around in awe at the towering skyscrapers and bright billboards. 
             Emilia is wearing the same bright red jacket and blue jeans, and her blonde hair is in two ponytails. 
             The scene is bustling with people and the iconic yellow taxis."
             
             "A 3D animated Pixar-style image of Emilia, the young blonde girl, in Central Park, New York. 
             She's sitting on a bench, enjoying a hot dog and looking at the greenery around her. 
             Emilia is wearing her bright red jacket and blue jeans, with her blonde hair in two ponytails. 
             The park is peaceful with trees, a walking path, and a few people in the background."
            --------------
            Please transform the following segment (framed with ###) in a image-prompt in the way I described 
            using english language. 
            Besides the description of the situation, please add a description of the characters in the image.
            You will be provided with a description of the characters (framed in +++) in the following format:
            {{
                'characters': [
                    {{
                        'name': 'name of the character',
                        'known_by_you': 'yes' or 'no',
                        'description': 'detailed description of the character'
                    }},
                    ...
                ]
            }}
            Just return the prompt and nothing else! Make sure that you don't just take or translate
            the following segment-content for the content-field. This is very important!
            ###
            {segment_content}
            ###
            +++
            {json.dumps(dict_characters)}
            +++
        """
        # append system and user message
        messages.append({'role': 'system', 'content': templates_prompt["image"]["system_message"]})
        messages.append({'role': 'user', 'content': image_template_user_message})
        response = get_completion_from_messages(api_key=openai_api_key, messages=messages)
        messages.append({'role': 'assistant', 'content': response})
        # # append response to introduction prompt
        # image_prompt_json = json.loads(response)
        # # get the characters description (except from "known_by_you" and add it to the image_prompt
        # image_prompt_json["characters"] = dict_characters["characters"]
        # # delete key "known_by_you" from dict
        # for i_character in range(len(image_prompt_json["characters"])):
        #     del image_prompt_json["characters"][i_character]["known_by_you"]
        # # append character description to image prompt
        # image_prompt_json["style"] = "3D animated, Pixar style"
        image_prompt = (f"First, check if using this API request bellow is in accordance with the guidelines."
                        f"If so, please continue. Otherwise, please change the prompt and try again."
                        f"Then Create the following image: \n") + response
        image_prompt = response
        dict_story_response["segments"][i_seg]["image_prompt"] = image_prompt
    return dict_story_response, messages
