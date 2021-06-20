#!/usr/bin/env python3

import sys
import rospy
from std_msgs.msg import Bool
from tbd_audio_msgs.msg import VADStamped

THRESHOLD = 0.2  # Number of seconds before true gets published again


def main():

    rospy.init_node("agent_vad_speech_signal_merger", anonymous=True)

    threshold = rospy.Duration(secs=THRESHOLD)
    last_signal = None
    con_pub = rospy.Publisher('vad_out', VADStamped, queue_size=1)

    def signal_cb(msg: Bool):
        if (msg.data):
            nonlocal last_signal
            last_signal = rospy.Time.now()

    def vad_cb(msg: VADStamped):
        if last_signal is not None and (msg.header.stamp < last_signal or
                                        (msg.header.stamp - last_signal) < threshold):
            msg.is_speech = False
        con_pub.publish(msg)

    for topic_name in sys.argv:
        rospy.Subscriber(topic_name, Bool, signal_cb, queue_size=1)

    rospy.Subscriber('vad', VADStamped, vad_cb, queue_size=1)
    rospy.spin()


if __name__ == "__main__":
    main()
