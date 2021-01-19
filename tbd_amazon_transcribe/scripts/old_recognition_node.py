#!/usr/bin/env python3

import asyncio
import queue
import collections
import sys
import time

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent

import message_filters
import rospy
from tbd_audio_msgs.msg import AudioDataStamped, Utterance, VADStamped

tic = 0
toc = 0


class MyEventHandler(TranscriptResultStreamHandler):
    def __init__(self, output_stream, stream, pub):
        super().__init__(output_stream)
        self.transcript = None
        self.stream = stream
        # self._utterance_start_header = start_time
        # self._utterance_end_time = end_time
        self._pub = pub

    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        # This handler can be implemented to handle transcriptions as needed.
        # Here's an example to get started.
        hypothesis = None
        results = transcript_event.transcript.results
        for result in results:
            for alt in result.alternatives:
                print(alt.transcript)
                hypothesis = alt.transcript
                
                if not result.is_partial:
                    # await self.stream.input_stream.end_stream()
                    self.transcript = hypothesis

                    rospy.logdebug(f"result:{self.transcript}")

                    # self._ring_buffer.clear()

                    resp = Utterance()
                    # resp.header = self._utterance_start_header
                    resp.text = self.transcript
                    # resp.end_time = self._utterance_end_time
                    self._pub.publish(resp)
                    
            


class RecognitionNode(object):
    def __init__(self):

        self._speaking = False
        # self._running_stream = False

        # copied over code
        self._ring_buffer = collections.deque(maxlen=10)
        self._silent_ratio = 0.75
        self._speak_ratio = 0.75
        self._utterance_start_header = None
        self._stream = None

        self._vad_buffer = [None for i in range(25)]
        self._audio_buffer = [None for i in range(50)]

        self._start_transcribe = False

        # amazon transcribe client
        self._client = TranscribeStreamingClient(region='us-east-1')

        # queue to hold the audio chunks
        self._audio_chunks = queue.Queue()
        self._message_queue = queue.Queue()

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

    # OLD WRITE CHUNKS FUNCTION
    # async def _write_chunks(self):
    #     # keep writing while there is still speech
    #     while self._speaking:
    #         while not self._audio_chunks.empty() and self._stream is not None:
    #             await self._stream.input_stream.send_audio_event(audio_chunk=self._audio_chunks.get())

    #     await self._stream.input_stream.end_stream()
    #     rospy.logdebug("closing AWS Transcribe Stream")
    #     global tic
    #     tic = time.time()

    async def mic_stream(self):
        # This function wraps the raw input stream from the microphone forwarding
        # the blocks to an asyncio.Queue.

        while True:
            msg = self._message_queue.get()
            # audio = msg[0]
            # vad = msg[1]
        
            yield msg
                

    
    async def _write_chunks(self, stream):
        # This connects the raw audio chunks generator coming from the microphone
        # and passes them along to the transcription stream.
        vad_buffer = [None for i in range(50)]
        audio_buffer = [None for i in range(50)]
        # print(buffer)


        async for chunk in self.mic_stream():
            
            # if chunk != b'':
            #     await stream.input_stream.send_audio_event(audio_chunk=chunk)
            # else:
            #     print("Closing Stream")
            #     await stream.input_stream.end_stream()
            #     return
            
            ### WORKING CODE ###

            audio = chunk[0].data
            speaking = chunk[1].is_speech

            vad_buffer.pop(0)
            vad_buffer.append(speaking)
            audio_buffer.pop(0)
            audio_buffer.append(audio)
            

            if vad_buffer.count(True) > 30 and not self._speaking:
                print("Starting audio")
                self._speaking = True
                self._start_transcribe = False
                # print(buffer)
                for a in audio_buffer:
                    await stream.input_stream.send_audio_event(audio_chunk=a)
            elif vad_buffer.count(True) <= 20 and self._speaking:
                print("Stopped")
                self._speaking = False
                await stream.input_stream.end_stream()
                return
            elif self._speaking:
                # print('Sending speech')
                await stream.input_stream.send_audio_event(audio_chunk=audio)

            ### END WORKING CODE ###
 

    async def _run_transcribe(self):
        while True:

            if self._start_transcribe:    
                print("New Stream")

                # Start transcription to generate our async stream
                self._stream = await self._client.start_stream_transcription(
                    language_code="en-US",
                    media_sample_rate_hz=16000,
                    media_encoding="pcm",
                    vocabulary_name="tbd-podi"
                )
                rospy.logdebug("openning AWS Transcribe Stream")

                # Instantiate our handler and start processing events
                handler = MyEventHandler(self._stream.output_stream, self._stream, self._pub)

                await asyncio.gather(self._write_chunks(self._stream), handler.handle_events())

                # self._ring_buffer.clear()

                # if handler.transcript != None:
                #     resp = Utterance()
                #     resp.header = self._utterance_start_header
                #     resp.text = handler.transcript
                #     resp.end_time = self._utterance_end_time
                #     self._pub.publish(resp)

        # don't loop multiple times
        # self._utterance_start_header = None
        # self._speaking = False
        # self._audio_chunks = queue.Queue()
        # self._stream = None
        pass

    def _merge_audio(self, audio, vad):
        self._message_queue.put((audio, vad))
        
        self._vad_buffer.pop(0)
        self._vad_buffer.append(vad.is_speech)
        # # self._audio_buffer.pop(0)
        # # self._audio_buffer.append(audio.data)
        
        # # print(self._vad_buffer)

        if self._vad_buffer.count(True) > 15 and not self._start_transcribe and not self._speaking:
            print("Starting audio")
            self._start_transcribe = True
            # print(self._vad_buffer)
            # for a in self._audio_buffer:
            #     self._message_queue.put(a)
        # elif self._vad_buffer.count(True) <= 25 and self._speaking:
        #     print("Stopped")
        #     self._speaking = False
        #     # self._message_queue.put(b'')
        #     # self._audio_buffer = [None for i in range(100)]
        #     self._vad_buffer = [None for i in range(100)]
        # # elif self._speaking:
        # #     # print('Sending speech')
        # #     self._message_queue.put(audio.data)

        # if vad.is_speech:
        #     self._speaking = True
        # else:
        #     self._speaking = False

        # print(vad.is_speech)
        # if speaking
        # if self._speaking:

        #     # add to buffer
        #     self._ring_buffer.append((audio.data, vad))

        #     # add to the audio chunk queue since its still in speech
        #     # self._audio_chunks.put(audio.data)

        #     # if there is more silence, stop
        #     if len([v for a, v in self._ring_buffer if not v.is_speech]) > (self._silent_ratio * self._ring_buffer.maxlen):
        #         self._speaking = False
        #         self._utterance_end_time = max([v.header.stamp for a, v in self._ring_buffer if not v.is_speech])
        #         self._ring_buffer.clear()
        #         #print("Stoped Speaking ----------------------------")

        # # not running transcription
        # else:

        #     # add to the buffer
        #     self._ring_buffer.append((audio.data, vad))

        #     # if there is possible speech
        #     if len([v for a, v in self._ring_buffer if v.is_speech]) > (self._speak_ratio * self._ring_buffer.maxlen):

        #         # send the speech to the queue
        #         # for a, v in self._ring_buffer:
        #             # self._audio_chunks.put(a)

        #         self._speaking = True
        #         #print("Started Speaking >>>>>>>>>>>>>>>>>>>>>>>>")

        #         # utterance start time is the first VAD true signal
        #         self._utterance_start_header = [
        #             v for a, v in self._ring_buffer if v.is_speech].pop().header
        #         self._ring_buffer.clear()


if __name__ == '__main__':
    rospy.init_node("recognition_node", log_level=rospy.DEBUG)
    vad = RecognitionNode()
    rospy.spin()
