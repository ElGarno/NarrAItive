def prompt_templates(topic, children_age):
    story_template_general_system_message = """You are a narrative generator for children's books. It is your task to create
    a narrative for young children focusing on a certain topic. The creation consists of multiple steps. In the first
    step you will be provided with information about the topic and the age of the children and your task is to check
    if the main characters of the story are known to you. In the second step you will craft the narrative. And in the
    third step you will write image prompts for each chapter of the narrative.
    """
    # first step: check if characters are known
    prompt_check_user_input = f"""
    You will craft a narrative for young children focusing on a certain topic. 
    The story should be centered around {topic}. 
    Ideally, the narrative should revolve around subjects appealing to children of age {children_age}. 
    At first please extract the narratives' characters. Check if the characters
    are known by you.
    You must not return "yes" if you have just an imagination of the character. Please only answer with "yes" if 
    the character is public known and you know about every detail of it. If you have doubts, please answer with "no".
    Please return a json file with the following structure:
    {{
        'characters': [
            {{
                'name': 'name of the character',
                'known_by_you': 'yes' or 'no',
                'description': 'detailed description of the character - only if you know the character'
            }},
            ...
        ]
    }}
    """

    # """At first please extract the
    # narratives' characters. Check if every single one is known by you.
    # If not, please ask the user to describe the characters in more detail. Otherwise just continue.
    # Example: The 'ninja turtles or dagobert duck are well known characters. Also a group of animals like many ducks
    # or cows are well known. But if the user talks about a specific person or animal, you should ask for more details.
    # So if the input is like: A child named Justus who is visiting a zoo you should ask for more details."""
    story_template_create_system_message = """You are a narrative generator for children's books. Now you will 
    craft the narrative."""
    story_template_user_message = f"""
        Now you will craft the narrative.
        The narrative should be divided into ten (10) illustrative segments that are suitable to be accompanied by illustrations.
        The length of the segments should be between 50 and 100 words depending on the age of the child. Younger children prefer shorter story segments. 
        Please ensure that the language used is simple and lighthearted, with a touch of humor, and written in German. 
        The narrative should be vivid enough to inspire illustrative, yet not overly detailed, artwork. 
        Refer to the style exhibited in this message and the following examples while creating the story. 
        Return the story as a JSON file with the following structure:
        {{
            'title': 'Titel der Geschichte',
            'segments': [
                {{
                    'segment_id': 0,
                        'content': 'Inhalt von Segment 0 hier'
                }},
                {{
                    'segment_id': 1,
                        'content': 'Inhalt von Segment 1 hier'
                }},
                ...
            ]
        }}
        Make sure to write in german.
    """
    # prompt_check_user_input = f"""At first please extract the narratives' characters. Check if every single one
    # is known by you. If not, please ask the user to describe the characters in more detail. Otherwise just continue.
    # Example: The 'ninja turtles or dagobert duck are well known characters. Also a group of animals like many ducks
    # or cows are well known. But if the user talks about a specific person or animal, you should ask for more details.
    # So if the input is like: A child named Justus who is visiting a zoo you should ask for more details."""
    image_template_system_message = """You are a prompt generator for the image generator dall_e_3."""
    return {
        "story": {
            "system_message_1": story_template_general_system_message,
            "user_message_1": prompt_check_user_input,
            "system_message_2": story_template_create_system_message,
            "user_message_2": story_template_user_message,
        },
        "image": {
            "system_message": image_template_system_message,
            "user_message": ""
        }
    }
