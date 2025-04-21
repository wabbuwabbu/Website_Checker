import os
import json
import time
import asyncio
from datetime import datetime, timezone
import ssl
from OpenSSL import crypto
import requests
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv


# Github config validation
def validate_config():
    """Ensure required environment variables exist"""
    required = ['TELEGRAM_TOKEN', 'CHAT_ID', 'WEBSITES']
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        raise ValueError(f"Missing env vars: {', '.join(missing)}")
    
    try:
        json.loads(os.getenv('WEBSITES'))
    except json.JSONDecodeError:
        raise ValueError("WEBSITES must be valid JSON")

# Load environment variables
load_dotenv()

def load_websites():
    websites_json = os.getenv("WEBSITES")
    if not websites_json:
        raise ValueError("WEBSITES environment variable not found!")
    return json.loads(websites_json)

WEBSITES = load_websites()
STATUS_FILE = "status.json"

def load_status():
    try:
        with open(STATUS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_status(status):
    with open(STATUS_FILE, 'w') as f:
        json.dump(status, f, indent=2)

def check_ssl_expiry(url):
    try:
        hostname = url.split('//')[-1].split('/')[0]
        cert = ssl.get_server_certificate((hostname, 443))
        x509 = crypto.load_certificate(crypto.FILETYPE_PEM, cert)
        expiry_bytes = x509.get_notAfter()
        
        if expiry_bytes is None:
            return "No expiry date"
            
        expiry_date = expiry_bytes.decode('ascii')
        expiry = datetime.strptime(expiry_date, '%Y%m%d%H%M%SZ').replace(tzinfo=timezone.utc)
        days_left = (expiry - datetime.now(timezone.utc)).days
        return days_left
    except Exception as e:
        return f"SSL Error: {str(e)}"

def check_website(website_config):
    result = {
        "online": False,
        "error": None,
        "latency": None,
        "status_code": None,
        "ssl_days_remaining": None,
        "content_valid": None
    }
    
    try:
        start = time.time()
        response = requests.get(website_config["url"], timeout=10)
        latency = round((time.time() - start) * 1000)
        
        result.update({
            "status_code": response.status_code,
            "latency": latency,
            "online": response.status_code == 200,
            "content_valid": check_content(response, website_config.get("validation_text")),
            "ssl_days_remaining": check_ssl_expiry(website_config["url"])
        })
        
    except Exception as e:
        result["error"] = str(e)
    
    return result

def check_content(response, validation_text=None):
    if validation_text:
        return validation_text in response.text
    return True

def calculate_uptime(site_data):
    total = site_data.get('total_checks', 1)
    successful = site_data.get('successful_checks', 0)
    return round((successful / total) * 100, 2)

def create_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Full Status", callback_data="full_status"),
         InlineKeyboardButton("SSL Info", callback_data="ssl_info")]
    ])

async def send_alert(message):
    try:
        bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
        await bot.send_message(
            chat_id=os.getenv("CHAT_ID"),
            text=message,
            reply_markup=create_keyboard()
        )
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")

def main():
    status = load_status()
    
    for website in WEBSITES:
        current_status = check_website(website)
        site_name = website["name"]
        
        previous_data = status.get(site_name, {})
        total_checks = previous_data.get('total_checks', 0) + 1
        successful_checks = previous_data.get('successful_checks', 0)
        alert_sent = previous_data.get('alert_sent', False)
        was_online = previous_data.get('online', True)

        if current_status["online"]:
            successful_checks += 1

        site_status = {
            **current_status,
            "last_check": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "total_checks": total_checks,
            "successful_checks": successful_checks,
            "uptime": calculate_uptime({
                "total_checks": total_checks,
                "successful_checks": successful_checks
            }),
            "alert_sent": alert_sent
        }

        # Send "DOWN" alert
        if not current_status["online"] and was_online and not alert_sent:
            alert_msg = (
                f"⚠️ {site_name} is DOWN\n"
                f"URL: {website['url']}\n"
                f"Error: {current_status.get('error', 'Unknown error')}\n"
                f"Last Online: {previous_data.get('last_check', 'Never')}"
            )
            asyncio.run(send_alert(alert_msg))
            site_status["alert_sent"] = True

        # Send "BACK UP" alert
        elif current_status["online"] and not was_online and alert_sent:
            recovery_msg = (
                f"✅ {site_name} is BACK UP\n"
                f"URL: {website['url']}\n"
                f"Response Time: {current_status['latency']}ms\n"
                f"Status Code: {current_status['status_code']}"
            )
            asyncio.run(send_alert(recovery_msg))
            site_status["alert_sent"] = False

        status[site_name] = site_status

    save_status(status)

if __name__ == "__main__":
    validate_config()
    main()
