# Change log

## [0.2.0] - 2020-10-03
- **[Merged]** the amazon transcribe wrapper.
- **[Changed]** use DeepSpeech v0.8.2
- **[Added]** `Requirement.txt` that saves the version of python packages we are using.
- **[Added]** Utterance message now tells us the time it ends. `end_time`. Added support for it in both deepspeech + transcribe.

## [0.1.4] - 2020-09-30
- **[Added]** launch file to start the audio capture indepdendently.

## [0.1.3] - 2020-08-13
- Update to use DeepSpeech v0.8.1

## [0.1.2] - 2020-07-23
- Added `tbd_audio_speech_signal_relay` component that merged in bool signal from any TTS node and ignore speech if bool_signal is true.
- Added `confidence` to the Utterance message.

## [0.1.1] - 2020-06-26
- Added This changelog
- Added Setup instructions in `README.md`
- Update to use Deepspeech v0.7.4

## [0.1.0] - 2020-XX-XX
Initial Release.
