
import json
import requests
from django.conf import settings

import requests

def send_whatsapp_massage(phone_number, massage):
    url = "https://whats.easytech-sotfware.com/api/v1/send-text"

    params = {
            "token": settings.WHATSAPP_TOKEN,
            "instance_id": settings.WHATSAPP_ID,
            "msg": massage,
            "jid": f"2{phone_number}@s.whatsapp.net"
        }
    
    req = requests.get(url, params=params)
    
    return req.json()

