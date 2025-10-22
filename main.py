import sys
import time
import random
import logging
import requests
import datetime
import threading
import asyncio
import websockets
import json
import traceback
import signal
import os
from threading import Thread, Semaphore
from streamlink import Streamlink
from fake_useragent import UserAgent
from urllib.parse import urlparse

try:
    import tls_client
    HAS_TLS_CLIENT = True
except ImportError:
    HAS_TLS_CLIENT = False

class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[94m',     # Blue
        'INFO': '\033[92m',      # Green
        'WARNING': '\033[93m',   # Yellow
        'ERROR': '\033[91m',     # Red
        'CRITICAL': '\033[95m',  # Magenta
        'RESET': '\033[0m'       # Reset
    }
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        message = super().format(record)
        return f"{log_color}{message}{self.COLORS['RESET']}"

logger = logging.getLogger()
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)

ua = UserAgent()
CLIENT_TOKEN = "e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823"

class SimpleKickViewerBot:
    def __init__(self, channel_name, thread_count, proxy_file=None, proxy_type="all"):
        self.channel_name = self.extract_channel_name(channel_name)
        self.thread_count = int(thread_count)
        self.proxy_file = proxy_file
        self.proxy_type = proxy_type
        self.should_stop = False
        
        self.total_requests = 0
        self.active_connections = 0
        self.successful_connections = 0
        self.failed_connections = 0
        self.start_time = time.time()
        
        self.stats_lock = threading.Lock()
        
        self.proxies = []
        self.threads = []
        self.thread_semaphore = Semaphore(self.thread_count)
        
        self.channel_id = None
        self.livestream_id = None
        
        self.session = Streamlink()
        self.session.set_option("http-headers", {
            "User-Agent": ua.random,
            "Referer": "https://kick.com/"
        })
        
        signal.signal(signal.SIGINT, self.signal_handler)
        
    def signal_handler(self, signum, frame):
        logging.info("Received shutdown signal...")
        self.should_stop = True
        
    def extract_channel_name(self, input_str):
        if "kick.com/" in input_str:
            parts = input_str.split("kick.com/")
            channel = parts[1].split("/")[0].split("?")[0]
            return channel.lower()
        return input_str.lower()

    def print_banner(self):
        banner = """
==============================================
      MYLE VIEWBOT
==============================================
        """
        print(banner)

    def print_status(self):
        current_time = time.time()
        elapsed = current_time - self.start_time
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))
        
        rpm = (self.total_requests / elapsed * 60) if elapsed > 0 else 0
        total_attempts = self.successful_connections + self.failed_connections
        success_rate = (self.successful_connections / total_attempts * 100) if total_attempts > 0 else 0
        
        os.system("cls" if os.name == "nt" else "clear")

        print("\n" + "="*50)
        print("LIVE STATISTICS")
        print("="*50)
        print(f"Channel: {self.channel_name} | ID: {self.channel_id or 'Loading...'}")
        print(f"Connections: {self.active_connections}/{self.thread_count} Active")
        print(f"Success: {self.successful_connections} | Failed: {self.failed_connections}")
        print(f"Total Requests: {self.total_requests} | RPM: {rpm:.1f}")
        print(f"Success Rate: {success_rate:.1f}% | Proxies: {len(self.proxies)}")
        print(f"Elapsed Time: {elapsed_str}")
        print(f"Status: {'RUNNING' if not self.should_stop else 'STOPPING'}")
        print("="*50)
        print("Press CTRL+C to stop")
        print()

    def load_proxies(self):
        logging.info("Loading proxies...")
        
        if self.proxy_file and os.path.exists(self.proxy_file):
            try:
                with open(self.proxy_file, 'r', encoding='utf-8') as f:
                    lines = [line.strip() for line in f.readlines() if line.strip()]
                
                self.proxies = []
                for line in lines:
                    try:
                        if '://' in line:
                            self.proxies.append(line)
                        else:
                            self.proxies.append(f"http://{line}")
                    except Exception:
                        continue
                
                logging.info(f"Loaded {len(self.proxies)} proxies from file")
                return True
                
            except Exception as e:
                logging.error(f"Error loading proxy file: {e}")
                return False
        else:
            logging.info("Fetching proxies from API...")
            try:
                url = "https://api.proxyscrape.com/v4/free-proxy-list/get"
                params = {
                    'request': 'display_proxies',
                    'proxy_format': 'protocolipport',
                    'format': 'text',
                    'protocol': self.proxy_type,
                    'timeout': 10000
                }
                
                response = requests.get(url, params=params, timeout=30)
                if response.status_code == 200:
                    self.proxies = [f"http://{line.strip()}" for line in response.text.splitlines() if line.strip()]
                    logging.info(f"Loaded {len(self.proxies)} proxies from API")
                    return True
                else:
                    logging.error("Failed to fetch proxies from API")
                    return False
                    
            except Exception as e:
                logging.error(f"Error fetching proxies: {e}")
                return False

    def get_channel_id(self):
        logging.info("Getting channel information...")
        
        try:
            if HAS_TLS_CLIENT:
                try:
                    s = tls_client.Session(client_identifier="chrome_120", random_tls_extension_order=True)
                    s.headers.update({
                        'Accept': 'application/json, text/plain, */*',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Referer': 'https://kick.com/',
                        'Origin': 'https://kick.com',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Sec-Fetch-Dest': 'empty',
                        'Sec-Fetch-Mode': 'cors',
                        'Sec-Fetch-Site': 'same-origin',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                        'sec-ch-ua-mobile': '?0',
                        'sec-ch-ua-platform': '"Windows"',
                    })
                    response = s.get(f'https://kick.com/api/v2/channels/{self.channel_name}')
                    if response.status_code == 200:
                        data = response.json()
                        self.channel_id = data.get("id")
                        if 'livestream' in data and data['livestream']:
                            self.livestream_id = data['livestream'].get('id')
                            logging.info(f"Retrieved livestream ID: {self.livestream_id}")
                        logging.info(f"Retrieved channel ID from v2 API: {self.channel_id}")
                        return self.channel_id
                except Exception as e:
                    logging.debug(f"tls_client v2 API failed: {e}")
            
            try:
                headers = {
                    'User-Agent': ua.random,
                    'Accept': 'application/json',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Referer': f'https://kick.com/{self.channel_name}',
                }
                response = requests.get(f'https://kick.com/api/v1/channels/{self.channel_name}', 
                                      headers=headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    self.channel_id = data.get("id")
                    if 'livestream' in data and data['livestream']:
                        self.livestream_id = data['livestream'].get('id')
                        logging.info(f"Retrieved livestream ID: {self.livestream_id}")
                    logging.info(f"Retrieved channel ID from v1 API: {self.channel_id}")
                    return self.channel_id
            except Exception as e:
                logging.debug(f"v1 API failed: {e}")
            
            try:
                headers = {
                    'User-Agent': ua.random,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
                response = requests.get(f'https://kick.com/{self.channel_name}', 
                                      headers=headers, timeout=15, allow_redirects=True)
                if response.status_code == 200:
                    import re
                    patterns = [
                        r'"id":(\d+).*?"slug":"' + self.channel_name + r'"',
                        r'"channel_id":(\d+)',
                        r'channelId["\']:\s*(\d+)',
                        r'channel.*?id["\']:\s*(\d+)'
                    ]
                    
                    for pattern in patterns:
                        match = re.search(pattern, response.text, re.IGNORECASE)
                        if match:
                            self.channel_id = int(match.group(1))
                            logging.info(f"Retrieved channel ID from page: {self.channel_id}")
                            return self.channel_id
            except Exception as e:
                logging.debug(f"Page scraping failed: {e}")
            
            logging.error(f"All methods failed to get channel ID for: {self.channel_name}")
            return None
            
        except Exception as e:
            logging.error(f"Error getting channel ID: {e}")
            return None

    def get_websocket_token(self):
        try:
            if HAS_TLS_CLIENT:
                try:
                    s = tls_client.Session(client_identifier="chrome_120", random_tls_extension_order=True)
                    s.headers.update({
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Connection': 'keep-alive',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    })
                    
                    session_resp = s.get("https://kick.com")
                    if session_resp.status_code != 200:
                        raise Exception("Session establishment failed")
                    
                    time.sleep(0.5)
                    
                    s.headers.update({
                        'Accept': 'application/json, text/plain, */*',
                        'Referer': 'https://kick.com/',
                        'X-CLIENT-TOKEN': CLIENT_TOKEN,
                    })
                    
                    response = s.get('https://websockets.kick.com/viewer/v1/token')
                    
                    if response.status_code == 200:
                        data = response.json()
                        token = data.get("data", {}).get("token")
                        if token:
                            return token
                except Exception as e:
                    logging.debug(f"tls_client token retrieval failed: {e}")
            
            session = requests.Session()
            initial_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            }
            
            session_resp = session.get("https://kick.com", headers=initial_headers, timeout=15)
            if session_resp.status_code != 200:
                return None
            
            time.sleep(0.5)
            
            token_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Referer': 'https://kick.com/',
                'X-CLIENT-TOKEN': CLIENT_TOKEN,
            }
            
            token_endpoints = [
                'https://websockets.kick.com/viewer/v1/token',
                'https://kick.com/api/websocket/token',
            ]
            
            for endpoint in token_endpoints:
                try:
                    response = session.get(endpoint, headers=token_headers, timeout=10)
                    if response.status_code == 200:
                        data = response.json()
                        token = data.get("data", {}).get("token") or data.get("token")
                        if token:
                            return token
                except Exception:
                    continue
            
            return None
            
        except Exception as e:
            logging.error(f"Error getting WebSocket token: {e}")
            return None

    def update_stats(self, connections=0, requests=0, success=0, failed=0):
        with self.stats_lock:
            self.active_connections += connections
            self.total_requests += requests
            self.successful_connections += success
            self.failed_connections += failed

    async def websocket_worker(self, proxy_url=None):
        connection_id = random.randint(1000, 9999)
        retry_count = 0
        max_retries = 3
        
        self.update_stats(connections=1)
        
        while not self.should_stop and retry_count < max_retries:
            try:
                token = self.get_websocket_token()
                if not token:
                    self.update_stats(connections=-1, failed=1)
                    return
                
                ws_url = f"wss://websockets.kick.com/viewer/v1/connect?token={token}"
                
                async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10) as websocket:
                    self.update_stats(success=1)
                    
                    handshake_msg = {
                        "type": "channel_handshake",
                        "data": {"message": {"channelId": self.channel_id}}
                    }
                    await websocket.send(json.dumps(handshake_msg))
                    
                    while not self.should_stop:
                        ping_msg = {"type": "ping"}
                        await websocket.send(json.dumps(ping_msg))
                        self.update_stats(requests=1)
                        
                        handshake_msg = {
                            "type": "channel_handshake", 
                            "data": {"message": {"channelId": self.channel_id}}
                        }
                        await websocket.send(json.dumps(handshake_msg))
                        self.update_stats(requests=1)
                        
                        await asyncio.sleep(14)
                        
            except Exception as e:
                retry_count += 1
                if not self.should_stop and retry_count < max_retries:
                    await asyncio.sleep(2 ** retry_count)
                else:
                    self.update_stats(connections=-1, failed=1)
                    break

    def pstart_websocket_worker(self, proxy_url=None):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.websocket_worker(proxy_url))
        except Exception:
            self.update_stats(connections=-1, failed=1)
        finally:
            try:
                loop.close()
            except:
                pass

    def start_bot(self):
        self.print_banner()
        
        if not self.load_proxies():
            logging.error("Cannot start without proxies")
            return False
        
        if len(self.proxies) < self.thread_count:
            logging.warning(f"Only {len(self.proxies)} proxies for {self.thread_count} threads")
        
        self.channel_id = self.get_channel_id()
        if not self.channel_id:
            logging.error("Cannot start without channel ID")
            return False
        
        logging.info("Testing WebSocket authentication...")
        test_token = self.get_websocket_token()
        if not test_token:
            logging.error("Cannot get WebSocket token")
            return False
        logging.info("WebSocket authentication successful")
        
        logging.info(f"Starting {self.thread_count} WebSocket connections...")
        
        for i in range(self.thread_count):
            if self.should_stop:
                break
                
            if self.thread_semaphore.acquire(blocking=False):
                proxy = random.choice(self.proxies) if self.proxies else None
                thread = Thread(target=self.start_websocket_worker, args=(proxy,))
                thread.daemon = True
                thread.start()
                self.threads.append(thread)
                
                if i % 10 == 0 and i > 0:
                    time.sleep(0.5)
        
        self.monitor_connections()
        return True

    def monitor_connections(self):
        last_proxy_refresh = time.time()
        proxy_refresh_interval = 300
        
        logging.info("Bot is now running!")
        
        try:
            while not self.should_stop:
                self.print_status()
                
                self.threads = [t for t in self.threads if t.is_alive()]
                
                active_count = len([t for t in self.threads if t.is_alive()])
                if active_count < self.thread_count * 0.8 and not self.should_stop:
                    needed = self.thread_count - active_count
                    for i in range(needed):
                        if self.thread_semaphore.acquire(blocking=False):
                            proxy = random.choice(self.proxies) if self.proxies else None
                            thread = Thread(target=self.start_websocket_worker, args=(proxy,))
                            thread.daemon = True
                            thread.start()
                            self.threads.append(thread)
                
                if not self.proxy_file and time.time() - last_proxy_refresh >= proxy_refresh_interval:
                    logging.info("Refreshing proxies...")
                    self.load_proxies()
                    last_proxy_refresh = time.time()
                
                time.sleep(2)
                
        except KeyboardInterrupt:
            self.should_stop = True
        
        self.cleanup()

    def cleanup(self):
        logging.info("Shutting down bot...")
        self.should_stop = True
        
        for thread in self.threads:
            if thread.is_alive():
                thread.join(timeout=2)
        
        elapsed = time.time() - self.start_time
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))
        
        print("\n" + "="*50)
        print("FINAL STATISTICS")
        print("="*50)
        print(f"Total Runtime: {elapsed_str}")
        print(f"Total Requests: {self.total_requests}")
        print(f"Successful Connections: {self.successful_connections}")
        print(f"Failed Connections: {self.failed_connections}")
        print(f"Average RPM: {(self.total_requests / elapsed * 60) if elapsed > 0 else 0:.1f}")
        print("="*50)
        logging.info("Bot shutdown complete")

def main():
    try:
        os.system('cls' if os.name == 'nt' else 'clear')
        
        print("KICK.TV VIEWER BOT - SIMPLE VERSION")
        print("=====================================")
        print()
        
        channel_name = input("Enter channel username or URL: ").strip()
        if not channel_name:
            logging.error("Channel name is required!")
            return
        
        thread_count = input("Enter number of viewers/threads (default 20): ").strip()
        if not thread_count:
            thread_count = "20"
        
        try:
            thread_count = int(thread_count)
            if thread_count <= 0:
                raise ValueError
        except ValueError:
            logging.error("Please enter a valid number!")
            return
        
        proxy_file = input("Enter proxy file path (or press Enter for auto-fetch): ").strip()
        if proxy_file and not os.path.exists(proxy_file):
            logging.error("Proxy file not found!")
            use_proxy_file = input("Continue without proxy file? (y/n): ").strip().lower()
            if use_proxy_file != 'y':
                return
            proxy_file = None
        
        print("\nConfiguration Summary:")
        print(f"  Channel: {channel_name}")
        print(f"  Threads: {thread_count}")
        print(f"  Proxy File: {proxy_file or 'Auto-fetch'}")
        print(f"  Proxy Type: all")
        print()
        
        confirm = input("Start the viewer bot? (y/n): ").strip().lower()
        if confirm != 'y':
            logging.info("Operation cancelled")
            return
        
        bot = SimpleKickViewerBot(
            channel_name=channel_name,
            thread_count=thread_count,
            proxy_file=proxy_file,
            proxy_type="all"
        )
        
        success = bot.start_bot()
        
        if not success:
            logging.error("Failed to start bot")
        
    except KeyboardInterrupt:
        logging.info("Operation cancelled by user")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")

if __name__ == "__main__":
    try:
        import colorama
        import streamlink
        import websockets
        import fake_useragent
    except ImportError as e:
        logging.error(f"Missing required package: {e}")
        logging.info("Please install: pip install colorama streamlink websockets fake-useragent requests")
        if input("Install now? (y/n): ").lower() == 'y':
            os.system("pip install colorama streamlink websockets fake-useragent requests")
        sys.exit(1)
    
    main()
