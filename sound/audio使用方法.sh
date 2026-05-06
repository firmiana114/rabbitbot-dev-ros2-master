创建docker, 并挂载项目目录-v (注意目录是否是模型位置)
docker run -it   --name sound_docker   --runtime nvidia   --gpus all   -e NVIDIA_DRIVER_CAPABILITIES=all   -e NVIDIA_VISIBLE_DEVICES=all   --device /dev/snd   -v /dev/snd:/dev/snd   --group-add audio   --network host   --ipc host \
    -v /mnt/ssd/navgation/projects:/data  --privileged  sound_docker_img:latest

一、使用stt
首先安装funasr，然后下载相关模型，参考sense-voice-small.txt下的内容
pip install funasr
(可能需要安装其他的依赖)
下载模型，放到docker内部能够访问的目录，并更改stt_server_funasr.py中的模型路径为该目录
modelscope download --model iic/speech_fsmn_vad_zh-cn-16k-common-pytorch --local_dir ./fsmn_vad
modelscope download --model iic/SenseVoiceSmall --local_dir ./SenseVoiceSmall
1.使用stt_server.py启动服务，监听28184端口，等待接收音频数据。
(这里需要硬件适配，可能自行查看当前有哪些硬件录音设备)
python stt_server.py
2.使用stt_client.py中的STTReceiver类创建一个接收器实例，进行语音转文本的处理，得到文本后再进行后续的处理。
在主文件中代码如下：
from stt_client import STTReceiver
# 1. 创建接收器实例（队列大小、端口可配置）
receiver = STTReceiver(maxsize=5, port=28184)
# 2. 启动后台服务（非阻塞）
receiver.start()
# 3. 获取识别文本和识别情感队列，消费数据
stt_queue = receiver.get_queue()
emotion_queue = receiver.get_emotion_queue()
# 4. 动态消费数据
text = stt_queue.get(timeout=0.1)
emotion = emotion_queue.get(timeout=0.1)

二、使用TTS
1.安装kokoro(可选)
pip install kokoro
使用tts_server_kokoro.py启动服务，监听28185端口，等待接收文本数据。
2.安装fish_speech(可选, 需要下载fish-speech源代码)
这部分要使用fish-speech源代码
首先寻找一个声音，利用fishspeech_voiceclone.py进行克隆，得到一个新的声音文件xxx.npy。
使用tts_server_fishspeech.py，指向该npy,启动服务，监听28185端口，等待接收文本数据。
3.上述两者共同的调用方法
使用tts_client.py中的TTSProducer类创建一个生产者实例，进行文本转语音的处理，得到语音数据后再进行后续的处理。
在主文件中代码如下：
from tts_client import TTSAgent
# 1. 创建生产者实例（队列大小、端口和服务要一致）
tts = TTSAgent("http://127.0.0.1:28185/v1")
# 2. 发送给server产生语音，会返回生成语音时间,第二个输入参数代表是否需要打断当前语音
duration = tts.tts_sound(text, True)