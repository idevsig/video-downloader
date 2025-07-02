import os
import toml
import argparse

def load_config():
    """加载配置，优先级：命令行参数 > 配置文件 > 环境变量 > 默认值"""
    # 默认配置
    default_config = {
        'MQTT_BROKER': 'test.mosquitto.org',
        'MQTT_PORT': 1883,
        'QOS_LEVEL': 0,
        'KEEPALIVE': 60,
        'MQTT_TOPIC_SUBSCRIBE': 'video/download/request',
        'MQTT_TOPIC_PUBLISH': 'video/download/complete',
        'MQTT_CLIENT_ID': 'video_downloader_client',
        'DOWNLOAD_DIR': 'downloads',
        'DOWNLOAD_PREFIX_URL': '',
        'MQTT_USERNAME': None,
        'MQTT_PASSWORD': None,

        'ARIA2_RPC_ENABLE': False,
        'ARIA2_RPC_HOST': 'http://localhost',
        'ARIA2_RPC_PORT': 6800,
        'ARIA2_RPC_TOKEN': '',
        'ARIA2_DOWNLOAD_DIR': 'aria2_downloads',
    }

    # 初始化配置
    config = default_config.copy()

    # 1. 加载环境变量（最低优先级）
    for key in default_config:
        env_value = os.getenv(key)
        if env_value is not None:
            try:
                if key in ('MQTT_PORT', 'QOS_LEVEL', 'KEEPALIVE', 'ARIA2_RPC_PORT', 'ARIA2_RPC_ENABLE'):
                    config[key] = int(env_value)  # 类型转换
                else:
                    config[key] = env_value
                print(f"Loaded {key} from environment: {env_value}")
            except ValueError as e:
                print(f"Invalid environment variable {key}: {env_value}, error: {e}")

    # 2. 加载配置文件（覆盖环境变量）
    config_file = 'config.toml'
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                file_config = toml.load(f)
            mqtt_section = file_config.get('mqtt', {})
            for key in default_config:
                if key in mqtt_section:
                    try:
                        if key in ('MQTT_PORT', 'QOS_LEVEL', 'KEEPALIVE'):
                            config[key] = int(mqtt_section[key])  # 类型转换
                        else:
                            config[key] = mqtt_section[key]
                        print(f"Loaded {key} from config file: {mqtt_section[key]}")
                    except ValueError as e:
                        print(f"Invalid value for {key} in {config_file}: {mqtt_section[key]}, error: {e}")

            aria2_rpc_section = file_config.get('aria2', {})
            for key in default_config:
                if key in aria2_rpc_section:
                    try:
                        if key in ('ARIA2_RPC_PORT', 'ARIA2_RPC_ENABLE'):
                            config[key] = int(aria2_rpc_section[key])  # 类型转换
                        else:
                            config[key] = aria2_rpc_section[key]
                        print(f"Loaded {key} from config file: {aria2_rpc_section[key]}")
                    except ValueError as e:
                        print(f"Invalid value for {key} in {config_file}: {aria2_rpc_section[key]}, error: {e}")

        except Exception as e:
            print(f"Failed to load config file {config_file}: {e}")

    print()

    # 3. 解析命令行参数（最高优先级）
    parser = argparse.ArgumentParser(description='Video Downloader MQTT Client')
    parser.add_argument('--mqtt-broker', help='MQTT Broker address')
    parser.add_argument('--mqtt-port', type=int, help='MQTT Broker port')
    parser.add_argument('--qos-level', type=int, help='QoS level (0, 1, or 2)')
    parser.add_argument('--keepalive', type=int, help='MQTT Keepalive interval')
    parser.add_argument('--subscribe-topic', help='MQTT subscribe topic')
    parser.add_argument('--publish-topic', help='MQTT publish topic')
    parser.add_argument('--client-id', help='MQTT client ID')
    parser.add_argument('--download-dir', help='Download directory')
    parser.add_argument('--download-prefix-url', help='Download prefix URL')
    parser.add_argument('--mqtt-username', help='MQTT username for authentication')
    parser.add_argument('--mqtt-password', help='MQTT password for authentication')
    parser.add_argument('--aria2-rpc-enable', type=int, help='Enable aria2 RPC (0 or 1)')
    parser.add_argument('--aria2-rpc-host', help='aria2 RPC host')
    parser.add_argument('--aria2-rpc-port', type=int, help='aria2 RPC port')
    parser.add_argument('--aria2-rpc-token', help='aria2 RPC token')
    parser.add_argument('--aria2-download-dir', help='aria2 RPC download directory')

    args = parser.parse_args()

    # 更新配置
    for key in default_config:
        arg_key = key.lower().replace('-', '_')  # 将大写下划线转换为小写连字符
        arg_value = getattr(args, arg_key, None)
        if arg_value is not None:
            try:
                config[key] = arg_value
                print(f"Loaded {key} from command line: {arg_value}")
            except ValueError as e:
                print(f"Invalid command-line argument {arg_key}: {arg_value}, error: {e}")

    # 转换 ARIA2_RPC_ENABLE 为布尔值
    config['ARIA2_RPC_ENABLE'] = bool(config['ARIA2_RPC_ENABLE'])

    # 验证配置
    if config['QOS_LEVEL'] not in (0, 1, 2):
        print(f"Invalid QOS_LEVEL: {config['QOS_LEVEL']}, defaulting to 0")
        config['QOS_LEVEL'] = 0
    if config['MQTT_PORT'] <= 0 or config['MQTT_PORT'] > 65535:
        print(f"Invalid MQTT_PORT: {config['MQTT_PORT']}, defaulting to 1883")
        config['MQTT_PORT'] = 1883
    if config['ARIA2_RPC_PORT'] <= 0 or config['ARIA2_RPC_PORT'] > 65535:
        print(f"Invalid ARIA2_RPC_PORT: {config['ARIA2_RPC_PORT']}, defaulting to 6800")
        config['ARIA2_RPC_PORT'] = 6800
    if not config['DOWNLOAD_DIR']:
        print("Invalid DOWNLOAD_DIR, defaulting to 'downloads'")
        config['DOWNLOAD_DIR'] = 'downloads'

    return config