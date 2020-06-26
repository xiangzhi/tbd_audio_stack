#!/usr/bin/env python3

import collections
import os
import threading
from os.path import join

import deepspeech
import numpy as np

import message_filters
import rospy
from tbd_audio_msgs.msg import AudioDataStamped, Utterance, VADStamped


class RecognitionNode(object):

    def __init__(self):

        # replace this '/home/prithupareek/sim_ws' with the path to your current catkin workspace
        self._model_dir = rospy.get_param('~model_dir','/home/prithupareek/sim_ws/src/tbd_audio_stack/tbd_audio_recognition_deepspeech/models/')
        self._beam_width = rospy.get_param('~beam_width', 500)
        self._lm_alpha = rospy.get_param('~lm_alpha', 0.75)
        self._lm_beta = rospy.get_param('~lm_beta', 1.85)
        
        self._model_path = os.path.join(self._model_dir,'deepspeech-0.7.4-models.pbmm')
        self._scorer_path = os.path.join(self._model_dir, 'deepspeech-0.7.4-models.scorer')

        self._deep_speech = deepspeech.Model(self._model_path)
        self._deep_speech.enableExternalScorer(self._scorer_path)
        self._context = self._deep_speech.createStream()
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

    """Resample the audio from uint8[]
    
    Returns:
        np.int16 -- [description]
    """
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
            self._context.feedAudioContent(self._resample_audio(audio.data))
            # if there is more silence, stop
            if len([v for a, v in self._ring_buffer if not v.is_speech]) > (self._silent_ratio * self._ring_buffer.maxlen):
                # DONE
                # might want to add this to a seperate thread
                #print("Running model")
                #text = self._deep_speech.finishStream(self._context)
                data = self._context.finishStreamWithMetadata().transcripts[0]
                string_list = []
                timing_list = []
                curr_str = ""
                curr_str_time = 0

                for token in data.tokens:
                    if token.text == " ":
                        string_list.append(curr_str)
                        timing_list.append(curr_str_time)
                        curr_str = ""
                    else:
                        if curr_str == "":
                            curr_str_time = token.timestep
                        curr_str += token.text
                if curr_str != "":
                    string_list.append(curr_str)
                    timing_list.append(curr_str_time)        
                    
                self._context = self._deep_speech.createStream()
                resp = Utterance()
                resp.header = self._utterance_start_header
                resp.text = " ".join(string_list)
                resp.word_list = string_list
                resp.timing_list = timing_list
                self._pub.publish(resp)

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
                    self._context.feedAudioContent(self._resample_audio(a))
                self._running = True
                # the utterance start time is the first VAD true signal
                self._utterance_start_header = [v for a, v in self._ring_buffer if v.is_speech].pop().header
                self._ring_buffer.clear()


if __name__ == '__main__':
    rospy.init_node("recognition_node")
    vad = RecognitionNode()
    rospy.spin()
