#include <cstdlib>
#include <iostream>
#include <string>

#include <unitree/robot/channel/channel_factory.hpp>
#include <unitree/robot/g1/audio/g1_audio_client.hpp>

namespace {

void PrintUsage(const char* program) {
  std::cerr << "用法: " << program
            << " --network <网卡名> --text <播报文本> [--speaker <编号>]"
            << " [--volume <0-100>] [--timeout <秒>]" << std::endl;
}

bool ReadNextValue(int argc, char** argv, int* index, std::string* value) {
  if (*index + 1 >= argc) {
    return false;
  }
  *value = argv[++(*index)];
  return true;
}

int ParseInt(const std::string& value, const std::string& name) {
  try {
    return std::stoi(value);
  } catch (const std::exception& exc) {
    std::cerr << "参数解析失败: name=" << name << ", value=" << value
              << ", error=" << exc.what() << std::endl;
    std::exit(2);
  }
}

float ParseFloat(const std::string& value, const std::string& name) {
  try {
    return std::stof(value);
  } catch (const std::exception& exc) {
    std::cerr << "参数解析失败: name=" << name << ", value=" << value
              << ", error=" << exc.what() << std::endl;
    std::exit(2);
  }
}

}  // namespace

int main(int argc, char** argv) {
  std::string network_interface;
  std::string text;
  int speaker_id = 0;
  int volume = -1;
  float timeout = 10.0F;

  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    std::string value;
    if (arg == "--network") {
      if (!ReadNextValue(argc, argv, &i, &network_interface)) {
        PrintUsage(argv[0]);
        return 2;
      }
    } else if (arg == "--text") {
      if (!ReadNextValue(argc, argv, &i, &text)) {
        PrintUsage(argv[0]);
        return 2;
      }
    } else if (arg == "--speaker") {
      if (!ReadNextValue(argc, argv, &i, &value)) {
        PrintUsage(argv[0]);
        return 2;
      }
      speaker_id = ParseInt(value, "speaker");
    } else if (arg == "--volume") {
      if (!ReadNextValue(argc, argv, &i, &value)) {
        PrintUsage(argv[0]);
        return 2;
      }
      volume = ParseInt(value, "volume");
    } else if (arg == "--timeout") {
      if (!ReadNextValue(argc, argv, &i, &value)) {
        PrintUsage(argv[0]);
        return 2;
      }
      timeout = ParseFloat(value, "timeout");
    } else if (arg == "--help" || arg == "-h") {
      PrintUsage(argv[0]);
      return 0;
    } else {
      std::cerr << "未知参数: " << arg << std::endl;
      PrintUsage(argv[0]);
      return 2;
    }
  }

  if (network_interface.empty() || text.empty()) {
    PrintUsage(argv[0]);
    return 2;
  }

  if (volume > 100) {
    volume = 100;
  }
  if (volume < -1) {
    volume = -1;
  }

  try {
    std::cout << "Unitree G1 TTS开始: network=" << network_interface
              << ", speaker=" << speaker_id << ", volume=" << volume
              << ", timeout=" << timeout << ", text_len=" << text.size()
              << std::endl;
    unitree::robot::ChannelFactory::Instance()->Init(0, network_interface);
    unitree::robot::g1::AudioClient client;
    client.Init();
    client.SetTimeout(timeout);

    if (volume >= 0) {
      int32_t volume_ret = client.SetVolume(static_cast<uint8_t>(volume));
      std::cout << "Unitree G1 设置音量完成: ret=" << volume_ret
                << ", volume=" << volume << std::endl;
      if (volume_ret != 0) {
        return volume_ret;
      }
    }

    int32_t ret = client.TtsMaker(text, speaker_id);
    std::cout << "Unitree G1 TTS请求完成: ret=" << ret << std::endl;
    return ret;
  } catch (const std::exception& exc) {
    std::cerr << "Unitree G1 TTS异常: " << exc.what() << std::endl;
    return 1;
  }
}
