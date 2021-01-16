#!/usr/bin/env python3

import asyncio
import queue
import collections
import sys

from base64 import b64encode
import websockets
from hashlib import sha256
import wave
import datetime
from typing import Union, Any, List, Optional, cast
import os
from pathlib import Path
import hashlib
import hmac
import base64
import urllib
import binascii
import requests


import json

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent

import message_filters
import rospy
from tbd_audio_msgs.msg import AudioDataStamped, Utterance, VADStamped

from hyper import HTTPConnection

# we are using the boto3 framework to use exisiting AWS infrastructure to get the code
from boto3 import Session
session = Session()
cred = session.get_credentials().get_frozen_credentials()

class RecognitionNode(object):
    def __init__(self):
        self._new_utterance_in_progress = False

        # copied over code
        self._ring_buffer = collections.deque(maxlen=50)
        self._silent_ratio = 0.75
        self._speak_ratio = 0.75
        self._utterance_start_header = None

        # queue to hold the audio chunks
        self._audio_chunks = queue.Queue()

        # list to hold the results
        self._results = []

        self._pub = rospy.Publisher('/utterance', Utterance, queue_size=1)
        self._audio_sub = message_filters.Subscriber(
            'audioStamped', AudioDataStamped)
        self._vad_sub = message_filters.Subscriber('vad', VADStamped)

        self._ts = message_filters.TimeSynchronizer(
            [self._audio_sub, self._vad_sub], 10)

        # this might need to change, idk TODO
        self._ts.registerCallback(self._merge_audio)

        self._t = datetime.datetime.utcnow()
        self._request_url = self._create_request_url(self._t)

        # print(self._request_url)

        # r = requests.post(self._request_url)
        # print(r.text)

        conn = HTTPConnection('transcribestreaming.us-east-1.amazonaws.com')
        conn.request('POST', '/stream-transcription')
        resp = conn.get_response()

        print(resp.read())

        rospy.loginfo("Amazon Transcribe Started")

        # create the event loop and run the async code
        # self._loop = asyncio.new_event_loop()
        # self._loop.run_until_complete(self._process(self._request_url))
        # self._loop.close()


    # Key derivation functions. See:
    # http://docs.aws.amazon.com/general/latest/gr/signature-v4-examples.html#signature-v4-examples-python
    def _sign(self, key, msg):
        return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

    def _get_signature_key(self, key, dateStamp, regionName, serviceName):
        kDate = self._sign(('AWS4' + key).encode('utf-8'), dateStamp)
        kRegion = self._sign(kDate, regionName)
        kService = self._sign(kRegion, serviceName)
        kSigning = self._sign(kService, 'aws4_request')
        return kSigning

    # based on example at
    # https://docs.aws.amazon.com/transcribe/latest/dg/websocket.html
    def _create_request_url(self, t: datetime.datetime) -> str:

        ## Basic Information
        ACCESSS_KEY = cred.access_key
        SECRET_KEY = cred.secret_key
    
        # HTTP verb
        METHOD = "POST"
        VERSION = "HTTP/2.0"
        # Service name
        SERVICE = "transcribe"
        # AWS Region
        REGION = "us-east-1"
        # Amazon Transcribe streaming endpoint
        ENDPOINT = "/stream-transcription"
        # Host
        HOST = "transcribestreaming." + REGION + ".amazonaws.com"
        CONTENT_TYPE = "application/vnd.amazon.eventstream"
        AMZ_TARGET = "com.amazonaws.transcribe.Transcribe.StartStreamTranscription"
        AMZ_CONTENT_SHA256 = "STREAMING-AWS4-HMAC-SHA256-EVENTS"
        # Date and time of request
        amz_date = t.strftime('%Y%m%dT%H%M%SZ')
        datestamp = t.strftime('%Y%m%d')
        LANGUAGE_CODE = "en-US"
        MEDIA_ENCODING = "pcm"
        SAMPLE_RATE = "16000"
        TRANSFER_ENCODING = "chunked"

        ## create the canonical reqeust
        canonical_uri = ENDPOINT + "\n"
        canonical_headers = "content-type:" + CONTENT_TYPE + "\n"
        canonical_headers += "host:" + HOST + "\n"
        canonical_headers += "transfer-encoding:" + TRANSFER_ENCODING + "\n"
        canonical_headers += "x-amz-content-sha256:" + AMZ_CONTENT_SHA256 + "\n"
        canonical_headers += "x-amz-date:" + amz_date + "\n"
        canonical_headers += "x-amz-target:" + AMZ_TARGET + "\n"
        canonical_headers += "x-amzn-transcribe-language-code:" + LANGUAGE_CODE + "\n"
        canonical_headers += "x-amzn-transcribe-media-encoding:" + MEDIA_ENCODING + "\n"
        canonical_headers += "x-amzn-transcribe-sample-rate:" + SAMPLE_RATE + "\n"

        signed_headers = 'content-type;host;transfer-encoding;x-amz-content-sha256;x-amz-date;x-amz-target;x-amzn-transcribe-language-code;x-amzn-transcribe-media-encoding;x-amzn-transcribe-sample-rate'
        canonical_request = METHOD + '\n' + canonical_uri + '\n' + canonical_headers + '\n' + signed_headers + '\n' + AMZ_CONTENT_SHA256

        # print("Canonical Request")
        # print(canonical_request + '\n')

        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = datestamp + "/" + REGION + "/" + SERVICE + "/" + "aws4_request"
        
        ## (2) Create the String to Sign
        string_to_sign = algorithm + "\n" \
            + amz_date + "\n" \
            + credential_scope + "\n" \
            + hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()

        # print("String to Sign")
        # print(string_to_sign + '\n')

        ## (3) Calculate the Signature
        signing_key = self._get_signature_key(SECRET_KEY, datestamp, REGION, SERVICE)
        # Sign the string_to_sign using the signing_key
        signature = hmac.new(signing_key, (string_to_sign).encode('utf-8'), hashlib.sha256).hexdigest()
        # print("Signature")
        # print(signature + '\n')

        authorization_header = algorithm + " Credential=" + ACCESSS_KEY + "/" + credential_scope + ",SignedHeaders=" + signed_headers + ',Signature=' + signature
        # print("Authorization Header")
        # print(authorization_header + '\n')

        ## (4) add signing information to the request and create the request url
        canonical_headers += "Authorization:" + authorization_header
        request_url = 'https://' + HOST + canonical_uri + canonical_headers

        return request_url
        # return "http://transcribestreaming.us-east-1.amazonaws.com/stream-transcription"

    def _encode_header(self, name, value_type, value_string):
        payload = (len(name)).to_bytes(1, byteorder='big')
        payload += name.encode('utf-8')
        payload += (value_type).to_bytes(1, byteorder='big')
        payload += (len(value_string)).to_bytes(2, byteorder='big')
        payload += value_string.encode('utf-8')
        return payload

    def _create_audio_frame(self, audio_data: bytes) -> bytes:

        # create the data payload
        # headers
        header = self._encode_header(':content-type',7, 'application/octet-stream')
        header += self._encode_header(':event-type',7, 'AudioEvent')
        header += self._encode_header(':message-type',7, 'event')

        header_len = int(len(header)).to_bytes(4, byteorder='big')
        total_len = int(len(audio_data) + len(header) + 16).to_bytes(4, byteorder='big')

        msg = total_len + header_len
        msg += (binascii.crc32(msg)).to_bytes(4, byteorder='big')
        msg += header
        msg += audio_data
        msg += (binascii.crc32(msg)).to_bytes(4, byteorder='big')

        return msg

    def _get_response_in_json_format(self, response):
        decoded_string = response.decode("utf-8", "ignore")

        start = decoded_string.index('{')
        end = decoded_string.index(']}}') + 3

        decoded_string = decoded_string[start:end]

        decoded_string_json = json.loads(decoded_string)

        return decoded_string_json


    def get_transcript_from_response(self, response):

        decoded_string_json = self._get_response_in_json_format(response)

        if (len(decoded_string_json['Transcript']['Results']) > 0):
            transcript = decoded_string_json['Transcript']['Results'][0]['Alternatives'][0]['Transcript']
        else:
            transcript = ""

        return transcript

    async def _process(self, uri):
        while not rospy.is_shutdown():

            if self._new_utterance_in_progress:
                try:
                    async with websockets.connect(uri) as websocket:

                        while self._new_utterance_in_progress:
                            while not self._audio_chunks.empty():
                                audio_data = self._audio_chunks.get()
                                msg = self._create_audio_frame(audio_data)
                                await websocket.send(msg)

                            # add a loop for receive messages
                            try:
                                result = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                                self._results += [result]
                            except asyncio.TimeoutError:
                                pass

                        msg = self._create_audio_frame(b'')
                        await websocket.send(msg)

                        while not rospy.is_shutdown():
                            result = await websocket.recv()
                            self._results += [result]
                            tic = rospy.Time.now()

                except websockets.ConnectionClosed as closed:

                    toc = rospy.Time.now()
                    delay = (toc - tic).to_sec()
                    rospy.logdebug(f"delay:{delay}")

                    if (len(self._results) != 0):
                        response = self._results[len(self._results) - 1]
                        
                        try:
                            transcript = self.get_transcript_from_response(response)

                            rospy.logdebug(f"receive transcript: {transcript}")

                            resp = Utterance()
                            resp.header = self._utterance_start_header
                            resp.text = transcript
                            resp.end_time = self._utterance_end_time
                            self._pub.publish(resp)
                            processing_time = (rospy.Time.now() - self._debug_ending_time).to_sec()
                            rospy.logdebug(f"processing time since end:{processing_time}")
                        except:
                            pass


                    self._utterance_start_header = None
                    self._new_utterance_in_progress = False
                    transcript = ""
                    self._audio_chunks = queue.Queue()
                    self._results = []

                    rospy.logdebug("connection finished")


    def _merge_audio(self, audio, vad):
        # print(vad.is_speech)
        # if speaking
        if self._new_utterance_in_progress:

            # add to buffer
            self._ring_buffer.append((audio.data, vad))

            # add to the audio chunk queue since its still in speech
            self._audio_chunks.put(audio.data)

            # if there is more silence, stop
            if len([v for a, v in self._ring_buffer if not v.is_speech]) > (self._silent_ratio * self._ring_buffer.maxlen):
                self._new_utterance_in_progress = False
                self._utterance_end_time = max([v.header.stamp for a, v in self._ring_buffer if not v.is_speech])
                self._ring_buffer.clear()
                self._debug_ending_time = rospy.Time.now()
                rospy.logdebug("Stopped Speaking ----------------------------")

        # not running transcription
        else:

            # add to the buffer
            self._ring_buffer.append((audio.data, vad))

            # if there is possible speech
            if len([v for a, v in self._ring_buffer if v.is_speech]) > (self._speak_ratio * self._ring_buffer.maxlen):

                # send the speech to the queue
                for a, v in self._ring_buffer:
                    self._audio_chunks.put(a)

                self._new_utterance_in_progress = True
                rospy.logdebug("Started Speaking >>>>>>>>>>>>>>>>>>>>>>>>")

                # utterance start time is the first VAD true signal
                self._utterance_start_header = [
                    v for a, v in self._ring_buffer if v.is_speech].pop().header
                self._ring_buffer.clear()


if __name__ == '__main__':
    rospy.init_node("recognition_node", log_level=rospy.DEBUG)
    vad = RecognitionNode()
    rospy.spin()
