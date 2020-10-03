#!/usr/bin/env python3

import asyncio
import queue
import collections
import sys

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent

import message_filters
import rospy
from tbd_audio_msgs.msg import AudioDataStamped, Utterance, VADStamped


class MyEventHandler(TranscriptResultStreamHandler):
    def __init__(self, output_stream):
        super().__init__(output_stream)
        self.transcript = None

    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        # This handler can be implemented to handle transcriptions as needed.
        # Here's an example to get started.
        hypothesis = None
        results = transcript_event.transcript.results
        for result in results:
            for alt in result.alternatives:
                # print(alt.transcript)
                hypothesis = alt.transcript
                pass

        if hypothesis != None:
            self.transcript = hypothesis


class RecognitionNode(object):
    def __init__(self):

        self._speaking = False
        # self._running_stream = False

        # copied over code
        self._ring_buffer = collections.deque(maxlen=50)
        self._silent_ratio = 0.75
        self._speak_ratio = 0.75
        self._utterance_start_header = None

        # amazon transcribe client
        self._client = TranscribeStreamingClient(region='us-east-1')

        # queue to hold the audio chunks
        self._audio_chunks = queue.Queue()

        self._pub = rospy.Publisher('/utterance', Utterance, queue_size=1)
        self._audio_sub = message_filters.Subscriber(
            'audioStamped', AudioDataStamped)
        self._vad_sub = message_filters.Subscriber('vad', VADStamped)

        self._ts = message_filters.TimeSynchronizer(
            [self._audio_sub, self._vad_sub], 10)
        self._ts.registerCallback(self._merge_audio)

        rospy.loginfo("Amazon Transcribe Started")

        # create the event loop and run the async code
        self._loop = asyncio.new_event_loop()
        self._loop.run_until_complete(self._run_transcribe())
        self._loop.close()

        rospy.loginfo("Amazon Transcribe Stopped")

    async def _write_chunks(self):
        while self._speaking:
            while not self._audio_chunks.empty():
                await self._stream.input_stream.send_audio_event(audio_chunk=self._audio_chunks.get())
                asyncio.sleep(0.01)  # TODO add condition for speaking
                # print(self._audio_chunks.qsize())
        await self._stream.input_stream.end_stream()
        print("Closed Stream", flush=True)

    async def _run_transcribe(self):
        while True:
            if self._speaking:

                # Start transcription to generate our async stream
                self._stream = await self._client.start_stream_transcription(
                    language_code="en-US",
                    media_sample_rate_hz=16000,
                    media_encoding="pcm",
                    vocabulary_name="tbd-podi"
                )
                print("Opened Stream", flush=True)

                # Instantiate our handler and start processing events
                handler = MyEventHandler(self._stream.output_stream)

                await asyncio.gather(self._write_chunks(), handler.handle_events())

                print(handler.transcript)

                if handler.transcript != None:
                    resp = Utterance()
                    resp.header = self._utterance_start_header
                    resp.text = handler.transcript
                    resp.end_time = self._utterance_end_time
                    self._pub.publish(resp)

                # don't loop multiple times
                self._utterance_start_header = None
                self._speaking = False
                self._audio_chunks = queue.Queue()

    async def _test_async(self):
        while True:
            while not self._audio_chunks.empty():
                # print(self._audio_chunks.get())
                self._audio_chunks.get()
                print(self._audio_chunks.qsize())
            # print("Done with speech")

    def _merge_audio(self, audio, vad):
        # print(vad.is_speech)
        # if speaking
        if self._speaking:

            # add to buffer
            self._ring_buffer.append((audio.data, vad))

            # add to the audio chunk queue since its still in speech
            self._audio_chunks.put(audio.data)

            # if there is more silence, stop
            if len([v for a, v in self._ring_buffer if not v.is_speech]) > (self._silent_ratio * self._ring_buffer.maxlen):
                self._speaking = False
                self._utterance_end_time = max([v.header.stamp for a, v in self._ring_buffer if not v.is_speech])
                self._ring_buffer.clear()
                print("Stoped Speaking ----------------------------")

        # not running transcription
        else:

            # add to the buffer
            self._ring_buffer.append((audio.data, vad))

            # if there is possible speech
            if len([v for a, v in self._ring_buffer if v.is_speech]) > (self._speak_ratio * self._ring_buffer.maxlen):

                # send the speech to the queue
                for a, v in self._ring_buffer:
                    self._audio_chunks.put(a)

                self._speaking = True
                print("Started Speaking >>>>>>>>>>>>>>>>>>>>>>>>")

                # utterance start time is the first VAD true signal
                self._utterance_start_header = [
                    v for a, v in self._ring_buffer if v.is_speech].pop().header
                self._ring_buffer.clear()


if __name__ == '__main__':
    rospy.init_node("recognition_node")
    vad = RecognitionNode()
    rospy.spin()
