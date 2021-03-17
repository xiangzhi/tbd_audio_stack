#!/usr/bin/env python3

import rospy
from std_msgs.msg import (
    Bool
)
from tbd_audio_msgs.msg import (
    FilterStamped,
    VADStamped
)
import webrtcvad

class WebRTCVadNode:

    def __init__(self):
        self._vad = webrtcvad.Vad()

        self._aggressiveness = rospy.get_param('~aggressiveness', 3)
        self._vad.set_mode(self._aggressiveness)

        self._sample_rate = rospy.get_param('~sample_rate', 16000)
        self._frame_duration = rospy.get_param('~frame_duration', 10)

        self._signal_pub = rospy.Publisher('vad', VADStamped, queue_size=5) 
        rospy.Subscriber('filterStamped', FilterStamped, self._audio_cb, queue_size=5)

    def _audio_cb(self, msg):

        audio_data = msg.filtered_data
        result = self._vad.is_speech(audio_data, self._sample_rate)

        response = VADStamped()
        response.header = msg.header
        response.is_speech = result
        self._signal_pub.publish(response)

if __name__ == '__main__':
    rospy.init_node("vad_node")
    vad = WebRTCVadNode()
    rospy.spin()
