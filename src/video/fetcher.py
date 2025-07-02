import paho.mqtt.client as mqtt
import json
import subprocess
import os
import time
import logging
import queue
import threading
from .logger import setup_logging
from .config import load_config
from .utils import extract_url_from_text, is_valid_m3u8_url

"""
Download videos to a cloud server with sequential MQTT message processing.
（此版本为 AI 优化，支持队列）
"""

def on_connect(client, userdata, flags, rc, *args, **kwargs):
    """MQTT connection callback, compatible with MQTT 3.1/3.1.1 and 5.0."""
    logging.info(f"Connected to MQTT broker with result code {rc}")
    if rc == 0:
        config = userdata['config']
        client.subscribe(config['MQTT_TOPIC_SUBSCRIBE'], qos=config['QOS_LEVEL'])
        logging.info(f"Subscribed to topic: {config['MQTT_TOPIC_SUBSCRIBE']} with QoS {config['QOS_LEVEL']}")
    else:
        logging.error(f"Failed to connect to MQTT broker: {rc}")

def on_message(client, userdata, msg):
    """MQTT message callback: Add messages to the queue for sequential processing."""
    logging.info(f"Received message on topic {msg.topic}: {msg.payload.decode()}")
    try:
        # Add message to the queue
        userdata['message_queue'].put((msg, time.time()))
        logging.info(f"Message queued for processing: {msg.payload.decode()}")
    except Exception as e:
        logging.error(f"Error queuing message: {str(e)}")


def download_video(url, output_path):
    """Download video using m3u8-downloader."""
    try:
        command = ['m3u8-downloader', '-u', url, '-o', output_path]
        logging.info(f"Executing command: {' '.join(command)}")
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="ignore",
            text=True
        )
        if result.returncode == 0:
            logging.info(f"Video downloaded successfully to {output_path}")
            return output_path
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
        
        # Parse message content
        try:
            data = json.loads(payload)
            url = data.get('url')
            name = data.get('name')
        except json.JSONDecodeError:
            url = extract_url_from_text(payload)
            name = None
        
        if not url:
            logging.warning("No valid URL found in the message")
            return
        
        if not is_valid_m3u8_url(url):
            logging.warning("No valid M3U8 URL found in the message")
            return

        logging.info(f"Extracted URL: {url}, Name: {name}")
        
        filename = name or f"video_{int(time.time())}"
        output_path = os.path.join(config['DOWNLOAD_DIR'], filename)
        download_url = f"{config['DOWNLOAD_PREFIX_URL']}{filename}.mp4"

        # Download video
        video_path = download_video(url, output_path)
        
        if video_path:
            # Publish success message
            complete_msg = {
                "status": "success",
                "url": url,
                "name": filename,
                "file_path": video_path,
                "download_url": download_url,
                "timestamp": int(time.time()),
                "receive_time": receive_time
            }
            result = client.publish(
                config['MQTT_TOPIC_PUBLISH'],
                json.dumps(complete_msg, ensure_ascii=False),
                qos=config['QOS_LEVEL']
            )
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logging.info(f"Published completion message for {url}")
            else:
                logging.error(f"Failed to publish completion message: {result.rc}")
        else:
            # Publish error message
            error_msg = {
                "status": "error",
                "url": url,
                "name": filename,
                "message": "Failed to download video",
                "timestamp": int(time.time()),
                "receive_time": receive_time
            }
            result = client.publish(
                config['MQTT_TOPIC_PUBLISH'],
                json.dumps(error_msg, ensure_ascii=False),
                qos=config['QOS_LEVEL']
            )
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logging.info(f"Published error message for {url}")
            else:
                logging.error(f"Failed to publish error message: {result.rc}")
                
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
    """Log MQTT client errors."""
    if paho_log_level == mqtt.LogLevel.MQTT_LOG_ERR:
        print(messages)

def main():
    service_name = "fetcher"
    
    # Load configuration
    config = load_config()
    
    # Configuration parameters
    MQTT_BROKER = config['MQTT_BROKER']
    MQTT_PORT = config['MQTT_PORT']
    QOS_LEVEL = config['QOS_LEVEL']
    KEEPALIVE = config['KEEPALIVE']
    MQTT_TOPIC_SUBSCRIBE = config['MQTT_TOPIC_SUBSCRIBE']
    MQTT_TOPIC_PUBLISH = config['MQTT_TOPIC_PUBLISH']
    suffix = time.strftime(f"_{service_name}_%y%m%d%H%M%S", time.localtime())
    MQTT_CLIENT_ID = config['MQTT_CLIENT_ID'] + suffix
    DOWNLOAD_DIR = config['DOWNLOAD_DIR']
    DOWNLOAD_PREFIX_URL = config['DOWNLOAD_PREFIX_URL']
    MQTT_USERNAME = config.get('MQTT_USERNAME', None)
    MQTT_PASSWORD = config.get('MQTT_PASSWORD', None)

    # Ensure download directory exists
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    # Setup logging
    setup_logging("fetcher")

    # Print configuration
    print("::Configuration loaded::")
    print(f"MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"QoS Level: {QOS_LEVEL}")
    print(f"Subscribe Topic: {MQTT_TOPIC_SUBSCRIBE}")
    print(f"Publish Topic: {MQTT_TOPIC_PUBLISH}")
    print(f"Client ID: {MQTT_CLIENT_ID}")
    print(f"Download Directory: {DOWNLOAD_DIR}")
    print(f"Download Prefix URL: {DOWNLOAD_PREFIX_URL}")
    print()

    # Create message queue and stop event
    message_queue = queue.Queue()
    stop_event = threading.Event()

    # Prepare userdata
    userdata = {
        'config': config,
        'message_queue': message_queue
    }

    # Create MQTT client
    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID, userdata=userdata)
    mqttc.reconnect_delay_set(min_delay=1, max_delay=120)

    # Set username and password if provided
    if MQTT_USERNAME and MQTT_PASSWORD:
        mqttc.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        logging.info(f"Using MQTT authentication: username={MQTT_USERNAME}")

    # Set callbacks
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
        # Connect to MQTT broker
        mqttc.connect(MQTT_BROKER, MQTT_PORT, keepalive=KEEPALIVE)
        logging.info(f"Connecting to MQTT broker: {MQTT_BROKER}:{MQTT_PORT}")
        mqttc.loop_start()  # Start MQTT loop in background thread
        while True:
            time.sleep(1)  # Keep main thread alive
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
    print("Starting MQTT video fetcher client...")
    main()