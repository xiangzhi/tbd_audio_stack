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
    def __init__(self, output_stream, stream, pub, caller):
        super().__init__(output_stream)
        self.transcript = None
        self.stream = stream
        # self._utterance_start_header = start_time
        # self._utterance_end_time = end_time
        self._pub = pub
        self._caller = caller

    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        # This handler can be implemented to handle transcriptions as needed.
        # Here's an example to get started.
        hypothesis = None
        results = transcript_event.transcript.results
        for result in results:
            for alt in result.alternatives:
                hypothesis = alt.transcript
                if not result.is_partial:
                    self.transcript = hypothesis

                    rospy.loginfo(f"result:{self.transcript}")

                    resp = Utterance()
                    #resp.header.stamp = self._caller.msg_start_time
                    resp.text = self.transcript
                    #resp.end_time = self._caller.msg_end_time
                    self._pub.publish(resp)
                    
            


class AWSTranscribeRecognitionNode(object):
    def __init__(self):

        self._speaking = False
        self._stream = None

        self._custom_vocabulary = rospy.get_param("~custom_vocabulary", default=None) 
        if (self._custom_vocabulary == "None" or self._custom_vocabulary == ""):
            self._custom_vocabulary = None
        rospy.logdebug(f"using custom vocabulary:{self._custom_vocabulary}")

        self._vad_buffer_size = 25
        self._vad_buffer = [None for i in range(0,self._vad_buffer_size)]
        self._transcribe_ratio = 0.8 

        self._start_transcribe_flag = threading.Event()
        self._stop_transcribe_flag = threading.Event()

        # amazon transcribe client
        self._client = TranscribeStreamingClient(region='us-east-1')

        # queue to hold the audio chunks
        self._audio_chunks = queue.Queue()
        self._message_queue = queue.Queue(maxsize=self._vad_buffer_size * 2)

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
        if (self._message_queue.qsize() >= self._message_queue.maxsize):
            self._message_queue.get()
        self._message_queue.put((audio, vad))
        
        # add vad_buffer to length
        self._vad_buffer.pop(0)
        self._vad_buffer.append(vad.is_speech)

        # start transcription if certain portion of the vad is true
        if self._vad_buffer.count(True)/len(self._vad_buffer) >= self._transcribe_ratio and not self._start_transcribe_flag.is_set():
            rospy.logdebug("Starting audio transcription")
            self._stop_transcribe_flag.clear()
            self._start_transcribe_flag.set()
        # stop transcription if the ratio goes down
        if (self._vad_buffer.count(False)/len(self._vad_buffer) >= self._transcribe_ratio) and self._start_transcribe_flag.is_set():
            self._start_transcribe_flag.clear()
            self._stop_transcribe_flag.set()



    async def audio_stream(self):
        # wraps incoming audio stream into async

        while not rospy.is_shutdown():
            try:
                msg = self._message_queue.get(timeout=0.1)
                yield msg
            except queue.Empty as e:
                pass
        raise rospy.ROSInterruptException("ROS Shutting")

            
    async def _write_chunks(self, stream):

        started = False
        async for chunk in self.audio_stream():
            
            audio = chunk[0].data
            vad = chunk[1].is_speech

            if started:
                # loop through if vad is false on the queue
                if not vad:
                    continue
                self.msg_start_time = chunk[1].header.stamp
                started = True
            
            # end if VAD is loser
            if self._stop_transcribe_flag.is_set():
                # The end time here is an estimate
                self.msg_end_time = chunk[1].header.stamp
                await stream.input_stream.end_stream()
                return 

            await stream.input_stream.send_audio_event(audio_chunk=audio) 


    async def _run_transcribe(self):

        while not rospy.is_shutdown():
            # wait for transcribe flag
            if self._start_transcribe_flag.wait(0.1):
                start_time = rospy.Time.now()
                # Start transcription to generate our async stream
                self._stream = await self._client.start_stream_transcription(
                    language_code="en-US",
                    media_sample_rate_hz=16000,
                    media_encoding="pcm",
                    vocabulary_name=self._custom_vocabulary
                )
                rospy.logdebug("Starting AWS Stream")
                # Instantiate our handler and start processing events
                handler = SpeechEventHandler(self._stream.output_stream, self._stream, self._pub, self)

                await asyncio.gather(self._write_chunks(self._stream), handler.handle_events())
                rospy.logdebug("Closing AWS Stream")
                self._start_transcribe_flag.clear()
                rospy.logdebug(f"Transcribe Time:{(rospy.Time.now() - start_time).to_sec()}")

    

if __name__ == '__main__':
    rospy.init_node("recognition_node", log_level=rospy.DEBUG)
    node = AWSTranscribeRecognitionNode()
    rospy.spin()
