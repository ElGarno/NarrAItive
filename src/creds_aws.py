from dotenv import load_dotenv
import os

load_dotenv()


class AWSConfig:
    AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY')
    AWS_SECRET_KEY = os.getenv('AWS_SECRET_KEY')




