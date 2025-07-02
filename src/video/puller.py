import aria2p
import paho.mqtt.client as mqtt
import json
import subprocess
import time
import logging
import queue
import threading
from .logger import setup_logging
from .config import load_config
from .utils import extract_url_from_text, is_valid_mp4_url

"""
下载到本地客户端
"""

def on_connect(client, userdata, flags, rc, *args, **kwargs):
    """MQTT 连接回调函数，兼容 MQTT 3.1/3.1.1 和 5.0"""
    logging.info(f"Connected to MQTT broker with result code {rc}")
    if rc == 0:
        # 从 userdata 获取配置
        config = userdata['config']
        client.subscribe(config['MQTT_TOPIC_PUBLISH'], qos=config['QOS_LEVEL'])
        logging.info(f"Subscribed to topic: {config['MQTT_TOPIC_PUBLISH']} with QoS {config['QOS_LEVEL']}")
    else:
        logging.error(f"Failed to connect to MQTT broker: {rc}")

def on_message(client, userdata, msg):
    """MQTT 消息回调函数"""
    logging.info(f"Received message on topic {msg.topic}: {msg.payload.decode()}")
    try:
        # Add message to the queue
        userdata['message_queue'].put((msg, time.time()))
        logging.info(f"Message queued for processing: {msg.payload.decode()}")
    except Exception as e:
        logging.error(f"Error queuing message: {str(e)}")

def download_video(download_url, config):
    """
    下载视频
    """
    if config['ARIA2_RPC_ENABLE']:
        download_video_aria2_rpc(download_url, config)
    else:
        download_video_cmd(download_url, config)

def download_video_aria2_rpc(download_url, config):
    """
    使用 aria2 RPC 下载视频
    """
    logging.info(f"Downloading video using aria2 RPC: {download_url}")
    try:
        aria2 = aria2p.API(
            aria2p.Client(
                host=config['ARIA2_RPC_HOST'],
                port=config['ARIA2_RPC_PORT'],
                secret=config['ARIA2_RPC_TOKEN']
            )
        )
    except Exception as e:
        logging.error(f"Error connecting to aria2 RPC: {str(e)}")
        return

    try:
        aria2.add_uris([download_url], options={
            'dir': config['ARIA2_DOWNLOAD_DIR'],
        })
        logging.info(f"Download started for {download_url}")
    except Exception as e:
        logging.error(f"Error adding download to aria2 RPC: {str(e)}")

def download_video_cmd(download_url, config):
    """
    使用命令行工具下载视频
    依赖 aria2c
    """
    logging.info(f"Downloading video using aria2c: {download_url}")
    try:
        # 你可以根据需要修改命令
        command = [
            'aria2c',
            '-x', '16',
            '-d', config['ARIA2_DOWNLOAD_DIR'],
            download_url,
        ]
        
        logging.info(f"Executing command: {' '.join(command)}")
        
        # 执行下载命令
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",          # 添加 encoding 时
            errors="ignore",           # 忽略非法字符            
            text=True
        )
        
        if result.returncode == 0:
            logging.info("Video downloaded successfully")
            return True
        else:
            logging.error(f"Failed to download video. Error: {result.stderr}")
            return None
            
    except Exception as e:
        logging.error(f"Error downloading video: {str(e)}")
        return None
    
def process_message(client, config, msg, receive_time):
    """Process a single MQTT message."""
    try:
        payload = msg.payload.decode('utf-8')
        logging.info(f"Processing message: {payload}")

        # 尝试解析为JSON
        try:
            data = json.loads(payload)
            download_url = data.get('download_url')
        except json.JSONDecodeError:
            # 如果不是JSON，尝试直接提取URL
            download_url = extract_url_from_text(payload)
        
        if not download_url:
            logging.warning("No valid URL found in the message")
            return
        
        if not is_valid_mp4_url(download_url):
            logging.warning(f"Invalid MP4 URL: {download_url}")
            return
            
        logging.info(f"Download URL: {download_url}")

        # 下载视频
        download_video(download_url, config)
            
    except Exception as e:
        logging.error(f"Error processing message: {str(e)}")        

def message_processor(client, userdata, stop_event):
    """Worker thread to process messages from the queue sequentially."""
    message_queue = userdata['message_queue']
    config = userdata['config']
    
    while not stop_event.is_set():
        try:
            # Get message from queue (block until a message is available or timeout)
            msg, receive_time = message_queue.get(timeout=1.0)
            logging.info("Dequeued message for processing")
            process_message(client, config, msg, receive_time)
            message_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            logging.error(f"Error in message processor: {str(e)}")

def on_log(client, userdata, paho_log_level, messages):
    if paho_log_level == mqtt.LogLevel.MQTT_LOG_ERR:
        print(messages)


def main():
    service_name = 'puller'

    config = load_config()
    
    # 配置参数
    MQTT_BROKER = config['MQTT_BROKER']
    MQTT_PORT = config['MQTT_PORT']
    QOS_LEVEL = config['QOS_LEVEL']
    KEEPALIVE = config['KEEPALIVE']
    # MQTT_TOPIC_SUBSCRIBE = config['MQTT_TOPIC_SUBSCRIBE']
    MQTT_TOPIC_PUBLISH = config['MQTT_TOPIC_PUBLISH']
    # yymmddhhiiss
    suffix = time.strftime(f"_{service_name}_%y%m%d%H%M%S", time.localtime())
    MQTT_CLIENT_ID = config['MQTT_CLIENT_ID'] + suffix
    # DOWNLOAD_DIR = config['DOWNLOAD_DIR']
    # DOWNLOAD_PREFIX_URL=config['DOWNLOAD_PREFIX_URL']

    MQTT_USERNAME = config.get('MQTT_USERNAME', None)
    MQTT_PASSWORD = config.get('MQTT_PASSWORD', None)

    ARIA2_RPC_ENABLE = config.get('ARIA2_RPC_ENABLE', False)

    ARIA2_RPC_HOST = config['ARIA2_RPC_HOST']
    ARIA2_RPC_PORT = config['ARIA2_RPC_PORT']
    ARIA2_RPC_TOKEN = config['ARIA2_RPC_TOKEN']
    ARIA2_DOWNLOAD_DIR = config['ARIA2_DOWNLOAD_DIR']

    # 确保下载目录存在
    # if not os.path.exists(DOWNLOAD_DIR):
    #     os.makedirs(DOWNLOAD_DIR)    

    # 设置日志    
    setup_logging(service_name)

    # 这里添加你的 MQTT 客户端逻辑
    print("::Configuration loaded::")
    print(f"MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"QoS Level: {QOS_LEVEL}")
    print(f"Subscribe Topic: {MQTT_TOPIC_PUBLISH}")
    print(f"Client ID: {MQTT_CLIENT_ID}")
    # print(f"Download Directory: {DOWNLOAD_DIR}")
    # print(f"Download Prefix URL: {DOWNLOAD_PREFIX_URL}")
    print(f"MQTT Username: {MQTT_USERNAME}")
    print(f"MQTT Password: {MQTT_PASSWORD}")
    print(f"ARIA2 RPC Enable: {ARIA2_RPC_ENABLE}")
    print(f"ARIA2 RPC Host: {ARIA2_RPC_HOST}")
    print(f"ARIA2 RPC Port: {ARIA2_RPC_PORT}")
    print(f"ARIA2 RPC Token: {ARIA2_RPC_TOKEN}")
    print(f"ARIA2 Download Dir: {ARIA2_DOWNLOAD_DIR}")
    print()

    config['MQTT_CLIENT_ID'] = MQTT_CLIENT_ID
    config['MQTT_USERNAME'] = MQTT_USERNAME
    config['MQTT_PASSWORD'] = MQTT_PASSWORD

    # Create message queue and stop event
    message_queue = queue.Queue()
    stop_event = threading.Event()

    # Prepare userdata
    userdata = {
        'config': config,
        'message_queue': message_queue
    }    

    # 创建MQTT客户端
    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID, userdata=userdata)
    mqttc.reconnect_delay_set(min_delay=1, max_delay=120)

    # 设置用户名和密码
    if MQTT_USERNAME and MQTT_PASSWORD:
        mqttc.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        logging.info(f"Using MQTT authentication: username={MQTT_USERNAME}")

    mqttc.on_log = on_log
    mqttc.on_connect = on_connect
    mqttc.on_message = on_message    

    # Start message processor thread
    processor_thread = threading.Thread(
        target=message_processor,
        args=(mqttc, userdata, stop_event),
        daemon=True
    )
    processor_thread.start()    

    try:
        mqttc.connect(MQTT_BROKER, MQTT_PORT, keepalive=KEEPALIVE)  # 增加 keepalive
        logging.info(f"Connecting to MQTT broker: {MQTT_BROKER}:{MQTT_PORT}")
        mqttc.loop_start()  # 在后台线程运行 MQTT 循环
        while True:
            time.sleep(1)  # 主线程保持运行
    except KeyboardInterrupt:
        logging.info("Received shutdown signal, stopping...")
        stop_event.set()  # Signal the processor thread to stop            
    except Exception as e:
        logging.error(f"Failed to connect or run MQTT client: {e}")
        raise
    finally:
        stop_event.set()  # Ensure processor thread stops
        mqttc.loop_stop()  # Stop MQTT loop
        mqttc.disconnect()  # Disconnect MQTT client
        processor_thread.join()  # Wait for processor thread to finish
        logging.info("MQTT client stopped.")

if __name__ == "__main__":
    print("Starting MQTT video puller client...")
    main()
