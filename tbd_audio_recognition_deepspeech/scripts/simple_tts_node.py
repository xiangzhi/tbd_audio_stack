#!/usr/bin/env python3

import rospy
from tbd_audio_msgs.msg import Utterance
from std_msgs.msg import String



if __name__ == "__main__":
    rospy.init_node("simple_converter")

    pub = rospy.Publisher("stt", String, queue_size=1)
    pub_msg = String()

    def callback(msg: Utterance):
        pub_msg.data = msg.text
        pub.publish(pub_msg)
    
    rospy.Subscriber("utterance", Utterance, callback, queue_size=1)

    rospy.spin()

