
import pyaudio


def list_pyaudio():
    p = pyaudio.PyAudio()

    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        print(
            f"{i}: {info['name']} "
            f"(host API: {info['hostApi']}, "
            f"max input channels: {info['maxInputChannels']}, "
            f"max output channels: {info['maxOutputChannels']})"
        )


if __name__ == "__main__":
    list_pyaudio()
