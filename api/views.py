from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.files.storage import FileSystemStorage
import os
from django.core.files.storage import default_storage
from rest_framework import status
from django.http import HttpResponse
from rest_framework.parsers import MultiPartParser
from utils.Utils import generate_summary
from .models import TextToVoice
from .serializers import *
from django.utils.crypto import get_random_string
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from PIL import Image
import pytesseract
import speech_recognition as sr
import pyttsx3
import moviepy.editor as mp
import speech_recognition as sr
from django.core.wsgi import get_wsgi_application
import pytesseract
import traceback
import logging
from django.core.files.base import ContentFile
from pydub import AudioSegment
from gtts import gTTS

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'server.settings')
logger = logging.getLogger(__name__)

application = get_wsgi_application()

class SummarizeText(APIView):
    def post(self,request,format=None):
        file = request.FILES.get("file")
        text = file.read().decode('utf-8')
        summary = generate_summary(text)

        return Response({"output": summary}, status=status.HTTP_200_OK)

class ImageToText(APIView):
    def post(self, request, format=None):
        image = request.FILES.get("image")
        if image:
            img = Image.open(image)
            text = pytesseract.image_to_string(img)
            if text:
                return Response({"output": text}, status=status.HTTP_200_OK)
        return Response({"Error While Processing Your Image"}, status=status.HTTP_400_BAD_REQUEST)


# class VoiceToText(APIView):
 
#     def post(self,request,format=None):
#         text = ""
#         audio_file = request.FILES.get('audio_file')
#         if audio_file:
#             content = audio_file.read()
#             # Sets the audio file's encoding and sample rate
#             client = speech.SpeechClient()
#             audio = speech.RecognitionAudio(content=content)
#             config = speech.RecognitionConfig(
#                 encoding=speech.RecognitionConfig.AudioEncoding.ENCODING_UNSPECIFIED,
#                 sample_rate_hertz=16000,  # Replace with your audio file's sample rate
#                 language_code='en-US'     # Replace with your audio file's language
#             )
#             response = client.recognize(config=config, audio=audio)
#             # Extract the transcribed text
#             for result in response.results:
#                 text += result.alternatives[0].transcript + ' '
#         return Response({"output": text }, status=status.HTTP_200_OK)



class VoiceToText(APIView):
    def post(self, request, format=None):
        audio_file = request.FILES.get("audio_file")
        if not audio_file:
            return Response({"Error": "Audio file is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Save the uploaded file temporarily
            fs = FileSystemStorage()
            original_file_name = audio_file.name
            file_name = default_storage.save(original_file_name, ContentFile(audio_file.read()))
            file_path = os.path.join(fs.location, file_name)
            
            # Define path for converted WAV file
            wav_file_path = os.path.splitext(file_path)[0] + ".wav"
            
            # Convert the audio file to WAV format using pydub
            try:
                sound = AudioSegment.from_file(file_path)
                # Export the audio in WAV format (PCM 16-bit)
                sound.export(wav_file_path, format="wav")
            except Exception as conv_e:
                # Cleanup original file before returning error
                default_storage.delete(file_name)
                return Response({"Error": "Failed to convert audio file: " + str(conv_e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Initialize recognizer and process the WAV file
            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_file_path) as source:
                audio_data = recognizer.record(source)
            
            # Use CMU Sphinx for offline recognition
            text = recognizer.recognize_sphinx(audio_data)
            
            # Cleanup temporary files
            default_storage.delete(file_name)
            if os.path.exists(wav_file_path):
                os.remove(wav_file_path)
            
            return Response({"output": text}, status=status.HTTP_200_OK)
        
        except sr.UnknownValueError:
            return Response({"Error": "Could not understand the audio"}, status=status.HTTP_400_BAD_REQUEST)
        except sr.RequestError:
            return Response({"Error": "Speech recognition service is unavailable"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({"Error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TextToAudio(APIView):
    def post(self, request, format=None):
        text = request.POST.get("text")
        if not text:
            return Response({"Error": "Text input is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Generate speech from text
            tts = gTTS(text=text, lang="en")
            file_name = "output.mp3"
            file_path = os.path.join(settings.MEDIA_ROOT, file_name)

            # Save the generated audio file
            tts.save(file_path)

            # Return a full media URL for access
            audio_url = request.build_absolute_uri(settings.MEDIA_URL + file_name)
            return Response({"output": audio_url}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"Error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class VideoToText(APIView):
    def post(self, request, format=None):
        video_file = request.FILES.get("video")
        if video_file:
            try:
                # Save video file to the local filesystem
                fs = FileSystemStorage()
                file_name = default_storage.save(video_file.name, video_file)
                video_path = os.path.join(fs.location, file_name)

                # Load the video file using moviepy
                video = mp.VideoFileClip(video_path)
                
                # Extract the audio from the video
                audio = video.audio
                audio_path = os.path.join(fs.location, f"{file_name}_output.wav")
                
                # Save audio as WAV file
                audio.write_audiofile(audio_path)
                video.close()  # Close the video clip

                # Create a recognizer instance for offline speech recognition
                recognizer = sr.Recognizer()
                with sr.AudioFile(audio_path) as source:
                    audio_data = recognizer.record(source)
                
                # Use CMU Sphinx (offline) for recognition
                text = recognizer.recognize_sphinx(audio_data)
                return Response({"output": text}, status=status.HTTP_200_OK)
            
            except sr.UnknownValueError:
                return Response({"Error": "Could not understand the audio"}, status=status.HTTP_400_BAD_REQUEST)
            except sr.RequestError:
                return Response({"Error": "Speech recognition service is unavailable"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception as e:
                # Log the exception for debugging purposes
                print("Error processing video to text:", e)
                return Response({"Error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({"Error": "Video file is required"}, status=status.HTTP_400_BAD_REQUEST)

