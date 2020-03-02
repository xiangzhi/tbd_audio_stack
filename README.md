# tbd_audio_stack
COPYRIGHT(C) 2020 - Transportation, Bots, and Disability Lab - CMU  
Code released under MIT.  
Contact - Zhi - zhi.tan@ri.cmu.edu

A collection of ROS Packages that handles audio processing from capture to recognition (Utterance). The collection consist of the following packages:

### tbd_audio_msgs
This repository consist of ROS Messages used throughout the collections

### tbd_audio_capture
Currently this is a republish of audio signal from audio_capture with our own message (`tbd_audio_msgs/AudioStamped`) which encodes the same data but adds additional information about originating time in the header.

### tbd_audio_vad
This package is a wrapper for WebRTCVADPy which conducts voice activity detection on the received stamped audio

### tbd_audio_recognition_deepspeech 
This package is a wrapper for Mozilla's open source implementation of [DeepSpeech](https://github.com/mozilla/DeepSpeech). It takes in both the VAD and Stamped audio and publishes a detected utterances.