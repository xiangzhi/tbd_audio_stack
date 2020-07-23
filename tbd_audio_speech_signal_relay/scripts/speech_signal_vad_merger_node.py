#!/usr/bin/env python3

import rospy
import message_filters
from std_msgs.msg import Bool
from tbd_audio_msgs.msg import VADStamped


def main():

    rospy.init_node("agent_vad_speech_signal_merger", anonymous=True)

    THRESHOLD = 0.15
    last_speech_signal = None
    con_pub = rospy.Publisher('vad_out', VADStamped)

    def signal_cb(msg: Bool):
        if (msg.data):
            nonlocal last_speech_signal
            last_speech_signal = rospy.Time.now()

    def vad_cb(msg: VADStamped):
        if last_speech_signal is not None and abs((msg.header.stamp - last_speech_signal).to_sec()) < THRESHOLD: 
            msg.is_speech = False
        con_pub.publish(msg)

    rospy.Subscriber('vad',VADStamped,vad_cb)
    rospy.Subscriber('agent_signal', Bool, signal_cb)

    rospy.spin()

if __name__ == "__main__":
    main()