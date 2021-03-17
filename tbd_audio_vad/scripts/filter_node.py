#!/usr/bin/env python3

# from os import pardir
# import pyaudio
# import wave
# import webrtcvad

import numpy as np
from matplotlib import pyplot as plt
from scipy.io import wavfile
from scipy.fft import rfft, rfftfreq, irfft, fft, ifft, fftfreq

import rospy
from std_msgs.msg import (
    Bool
)
from tbd_audio_msgs.msg import (
    AudioDataStamped,
    FilterStamped
)

class FilterNode:

    def __init__(self):

        self._min_freq = rospy.get_param('~min_freq', 0)
        self._max_freq = rospy.get_param('~max_freq', 500)

        self._sample_rate = rospy.get_param('~sample_rate', 16000)
        self._frame_duration = rospy.get_param('~frame_duration', .010) #10 ms

        self._min_freq_scaled = int(self._min_freq * self._frame_duration)
        self._max_freq_scaled = int(self._max_freq * self._frame_duration)

        self._signal_pub = rospy.Publisher('filterStamped', FilterStamped, queue_size=5) 
        rospy.Subscriber('audioStamped', AudioDataStamped, self._audio_cb, queue_size=5)

    def _audio_cb(self, msg):

        # convert the audio to numpy array
        audio_data = msg.data
        audio_data_numpy = np.frombuffer(audio_data, dtype=np.int16)

        # get the fft
        audio_data_fft = fft(audio_data_numpy)

        # 0 out the parts of the fft using bandpass filter
        audio_data_fft[0 : self._min_freq_scaled] = 0
        audio_data_fft[self._max_freq_scaled : 80] = 0
        audio_data_fft[80 : 160 - self._max_freq_scaled] = 0
        audio_data_fft[160 - self._min_freq_scaled : 160] = 0

        # create the fittered wave to send to the vad
        audio_data_numpy_new = ifft(audio_data_fft).astype('int16')
        audio_data_filtered = audio_data_numpy_new.tobytes()
            
        # fig, ax = plt.subplots(3,1)
        # x = fftfreq(len(audio_data_numpy), 1 / self._sample_rate)

        # # waveform and vad plotting on same plot
        # ax[0].plot(audio_data_numpy[0:])
        # # label the axes
        # ax[0].set_ylabel("Amplitude")
        # ax[0].set_xlabel("Time")
        # # set the title  

        # # plot the fft result
        # ax[1].plot(x, abs(audio_data_fft))
        # ax[1].set_ylabel('norm')
        # ax[1].set_xlabel('f (Hz)')

        # # plot the new wave
        # # waveform and vad plotting on same plot
        # ax[2].plot(audio_data_numpy_new[0:])
        # # label the axes
        # ax[2].set_ylabel("Amplitude")
        # ax[2].set_xlabel("Time")

        # ax[0].grid(); ax[1].grid(); ax[2].grid()

        # # display the plot
        # plt.show()

        # create the message with the filtered audio to be sent to the VAD
        response = FilterStamped()
        response.header = msg.header
        response.filtered_data = audio_data_filtered
        self._signal_pub.publish(response)

if __name__ == '__main__':
    rospy.init_node("filter_node")
    audio_filter = FilterNode()
    rospy.spin()
