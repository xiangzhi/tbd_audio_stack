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

## Quick 10-Step Setup Instructions

1. Install ROS Melodic.
2. Install these ROS dependencies:
   ```bash
   sudo apt install ros-melodic-audio-common*
   sudo apt install ros-melodic-audio-capture*
   ```
3. Install Python 3 dependencies:
    ```bash
    sudo apt install python3-venv
    ```
4. Create a new ros workspace and python3 virtual environment.
    ```bash
    mkdir catkin_ws && cd catkin_ws
    python3 -m venv venv
    source vevn/bin/activate
    ```
5. Install the following python3 dependencies into the virtual environment:
    ```bash
    pip install webrtcvad deepspeech==0.7.4 rospkg empy alloylib
    ```
6. Create and navigate to the `src` directory.
   ```bash
   mkdir src && cd src
   ```
7. Clone the `tbd_audio_stack` repo into `src`.
    ```bash
    git clone https://github.com/CMU-TBD/tbd_audio_stack.git
    ```
8. Download the correct deepspeech model files.
   ```bash
   cd src/tbd_audio_stack/tbd_audio_recognition_deepspeech && mkdir models && cd models
   wget https://github.com/mozilla/DeepSpeech/releases/download/v0.7.4/deepspeech-0.7.4-models.pbmm
   wget https://github.com/mozilla/DeepSpeech/releases/download/v0.7.4/deepspeech-0.7.4-models.scorer
   ```
9.  Go back to the workspaces's root directory and build and run your project. Make sure to be in the python3 virtual environment.
    ```bash
    cd ~/<path_to_your_workspace>/catkin_ws
    catkin build -DPYTHON_VERSION=3
    source devel/setup.bash
    roslaunch tbd_audio_recognition_deepspeech run_recognition.launch
    ```
10. Every thing sould run correctly, and you should be able to see the text output by running `rostopic echo /utterance` and speaking into your computers microphone.



