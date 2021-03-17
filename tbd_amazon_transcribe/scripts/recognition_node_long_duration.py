#!/usr/bin/env python3

import asyncio
import queue
import collections
import sys
import time
import threading

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent

import message_filters
import rospy
from tbd_audio_msgs.msg import AudioDataStamped, Utterance, VADStamped


class SpeechEventHandler(TranscriptResultStreamHandler):
    def __init__(self, output_stream, pub, caller):
        super().__init__(output_stream)
        self.transcript = None
        self._pub = pub
        self._caller = caller

    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        hypothesis = None
        results = transcript_event.transcript.results
        for result in results:
            for alt in result.alternatives:
                hypothesis = alt.transcript
                print(hypothesis)
                if not result.is_partial:
                    self.transcript = hypothesis

                    rospy.loginfo(f"result:{self.transcript}")

                    resp = Utterance()
                    #resp.header.stamp = self._caller.msg_start_time
                    resp.text = self.transcript
                    #resp.end_time = self._caller.msg_end_time
                    self._pub.publish(resp)
                    
            


class AWSTranscribeRecognitionNode(object):


    _message_queue: queue.Queue

    def __init__(self):

        self._speaking = False

        self._custom_vocabulary = rospy.get_param("~custom_vocabulary", default=None)
        self._custom_vocabulary = None if (self._custom_vocabulary == "" or self._custom_vocabulary == "None")  else self._custom_vocabulary 
        rospy.loginfo(f"using custom vocabulary:{self._custom_vocabulary}")


        # The vad buffer should be about 10 second long. 
        # Each incoming audio chunck is 10ms.
        self._vad_buffer_size = 100 * 10
        self._vad_buffer = [False for i in range(0,self._vad_buffer_size)]

        # Values of trigger
        self._transcribe_start_value_length_in_ms = 200
        self._transcribe_end_value_length_in_ms = 10000 #total silent for 3 seconds.

        self._start_transcribe_flag = threading.Event()
        self._end_transcribe_flag = threading.Event()

        # amazon transcribe client
        self._client = TranscribeStreamingClient(region='us-east-1')

        # queue to hold the audio chunks
        self._message_queue = queue.Queue(maxsize=int(self._transcribe_start_value_length_in_ms/10) + 10)

        self._pub = rospy.Publisher('/utterance', Utterance, queue_size=1)

        # merge the audio & vad signal
        self._audio_sub = message_filters.Subscriber(
            'audioStamped', AudioDataStamped)
        self._vad_sub = message_filters.Subscriber('vad', VADStamped)
        self._ts = message_filters.TimeSynchronizer(
            [self._audio_sub, self._vad_sub], 10)
        self._ts.registerCallback(self._audio_cb)

        rospy.loginfo("Amazon Transcribe Started")

        # create the event loop and run the async code
        self._loop = asyncio.new_event_loop()
        self._loop.run_until_complete(self._run_transcribe())
        self._loop.close()

        rospy.loginfo("Amazon Transcribe Stopped")

    def _audio_cb(self, audio, vad):

        # place message into queue
        if self._message_queue.qsize() >= self._message_queue.maxsize:
            self._message_queue.get()
        self._message_queue.put((audio, vad))
        
        # add vad to buffer
        self._vad_buffer.pop(0)
        self._vad_buffer.append(vad.is_speech)

        # initialize vad if its a certain condition
        if self._vad_buffer.count(True) >= self._transcribe_start_value_length_in_ms/10 and not self._start_transcribe_flag.is_set():
            rospy.logdebug("Starting audio transcription")
            self._start_transcribe_flag.set()
            self._end_transcribe_flag.clear()
        elif self._vad_buffer.count(False) >= self._transcribe_end_value_length_in_ms/10 and not self._end_transcribe_flag.is_set():
            rospy.logdebug("Attemping to Close AWS Stream")
            self._start_transcribe_flag.clear() 
            self._end_transcribe_flag.set()

    async def audio_stream(self):
        # wraps incoming audio stream into async

        while not rospy.is_shutdown():
            try:
                msg = self._message_queue.get(timeout=0.1)
                yield msg
            except Empty as e:
                pass
        raise rospy.ROSInterruptException("ROS Shutting")

            
    async def _write_chunks(self, stream):

        # first clear out all the chunks in the audio stream
        async for chunk in self.audio_stream():

            audio = chunk[0].data
            vad = chunk[1].is_speech
            # send to audio 
            await stream.input_stream.send_audio_event(audio_chunk=audio)

            if self._end_transcribe_flag.is_set():
                await stream.input_stream.end_stream()
                return


    async def _run_transcribe(self):

        while not rospy.is_shutdown():
            # wait for transcribe to start
            if self._start_transcribe_flag.is_set():
                # Start transcription to generate our async stream
                stream = await self._client.start_stream_transcription(
                    language_code="en-US",
                    media_sample_rate_hz=16000,
                    media_encoding="pcm",
                    vocabulary_name=self._custom_vocabulary
                )
                rospy.logdebug("Starting AWS Stream")
                # Instantiate our handler and start processing events
                handler = SpeechEventHandler(stream.output_stream, self._pub, self)
                # wait for it to end
                await asyncio.gather(self._write_chunks(stream), handler.handle_events())
                rospy.logdebug("Closing AWS Stream")


if __name__ == '__main__':
    rospy.init_node("recognition_node", log_level=rospy.DEBUG)
    node = AWSTranscribeRecognitionNode()
    rospy.spin()
