#!/usr/bin/env python3

import collections
import os
import threading
import typing

import deepspeech
import numpy as np

import message_filters
import rospy
from tbd_audio_msgs.msg import AudioDataStamped, Utterance, VADStamped


class RecognitionNode(object):

    def __init__(self):

        self._model_path = rospy.get_param('~model_path','/home/xiangzht/Data/Models/deepspeech/models.pbmm')
        self._scorer_path = rospy.get_param('~scorer_path','/home/xiangzht/Data/Models/deepspeech/models.scorer')
        self._beam_width = rospy.get_param('~beam_width', 500)
        self._publish_if_empty = rospy.get_param('~publish_if_empty', False)
        self._lm_alpha = rospy.get_param('~lm_alpha', 0.931289039105002)
        self._lm_beta = rospy.get_param('~lm_beta', 1.1834137581510284)
        
        self._deep_speech = deepspeech.Model(self._model_path)
        self._deep_speech.enableExternalScorer(self._scorer_path)
        self._deep_speech.setBeamWidth(self._beam_width)
        self._deep_speech.setScorerAlphaBeta(self._lm_alpha, self._lm_beta)

        self._stream = self._deep_speech.createStream()
        self._running = False

        self._ring_buffer = collections.deque(maxlen=50)
        self._silent_ratio = 0.75
        self._speak_ratio = 0.5
        self._utterance_start_header = None

        rospy.loginfo("Deep Speech Model Initialized")
        
        self._pub = rospy.Publisher('/utterance', Utterance, queue_size=1)

        audio_sub = message_filters.Subscriber('audioStamped', AudioDataStamped)
        vad_sub = message_filters.Subscriber('vad', VADStamped)

        ts = message_filters.TimeSynchronizer([audio_sub, vad_sub], 10)
        ts.registerCallback(self._merge_audio)


    def _resample_audio(self, ori_data):
        # new data
        new_buffer = np.zeros(int(len(ori_data)/2), dtype=np.int16)
        for i in range(0, int(len(ori_data)/2)):
            idx1 = (i * 2)
            idx2 = (i * 2) + 1
            buf = bytes([ori_data[idx1], ori_data[idx2]])
            new_buffer[i] = np.frombuffer(buf, np.int16)

        return new_buffer

    def _merge_audio(self, audio, vad):
        #print(vad.is_speech)
        if self._running:
            # add to buffer
            self._ring_buffer.append((audio.data, vad))
            # add to model since its still speech
            self._stream.feedAudioContent(self._resample_audio(audio.data))
            # if there is more silence, stop
            if len([v for a, v in self._ring_buffer if not v.is_speech]) > (self._silent_ratio * self._ring_buffer.maxlen):
                #TODO allow multiple results for comparison.
                data: deepspeech.Metadata
                data = self._stream.finishStreamWithMetadata()
                # Convert data into utterance response
                candidates: typing.List[deepspeech.CandidateTranscript]
                candidates = data.transcripts
                candidate = candidates[0]
                curr_str = ""
                curr_str_time = 0
                word_list = []
                timing_list = []
                for token in candidate.tokens:
                    # if its an space token, start a new word
                    if token.text == " ":
                        word_list.append(curr_str)
                        timing_list.append(curr_str_time)
                        curr_str = ""
                    else:
                        if curr_str == "":
                            curr_str_time = token.timestep
                        curr_str += token.text
                if curr_str != "":
                    word_list.append(curr_str)
                    timing_list.append(curr_str_time)                   

                #copy data & publish
                if self._publish_if_empty or len(word_list) > 0:
                    resp = Utterance()
                    resp.header = self._utterance_start_header
                    resp.confidence = candidate.confidence
                    resp.text = " ".join(word_list)
                    resp.timing_list = timing_list
                    resp.word_list = word_list
                    # calculate the end time. It is the last true VAD in the ROS 
                    resp.end_time = max([v.header.stamp for a, v in self._ring_buffer if not v.is_speech])
                    self._pub.publish(resp)

                # Create a new stream for the next set of inputs
                self._stream = self._deep_speech.createStream()

                self._running = False
                self._utterance_start_header = None
                self._ring_buffer.clear()
        else:
            # not running, but save chunk if it is running
            # add to buffer
            self._ring_buffer.append((audio.data, vad))
            if len([v for a, v in self._ring_buffer if v.is_speech]) > (self._speak_ratio * self._ring_buffer.maxlen):
                # this means its possible its speech
                for a,v in self._ring_buffer:
                    self._stream.feedAudioContent(self._resample_audio(a))
                self._running = True
                # the utterance start time is the first VAD true signal
                self._utterance_start_header = [v for a, v in self._ring_buffer if v.is_speech].pop().header
                self._ring_buffer.clear()


if __name__ == '__main__':
    rospy.init_node("recognition_node")
    vad = RecognitionNode()
    rospy.spin()
