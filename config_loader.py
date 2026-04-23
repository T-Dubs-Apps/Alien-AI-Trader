import json
import os

# Local config.json sits alongside this file (ignored by git via .gitignore)
CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'config.json'))

ENV_KEYS = [
    'ALPACA_KEY',
    'ALPACA_SECRET',
    'ALPHA_VANTAGE_KEY',
    'PUSHBULLET_TOKEN',
    'USER_EMAIL',
    'STRIPE_SECRET_KEY',
]

def load_config():
    config = {}
    for key in ENV_KEYS:
        value = os.getenv(key)
        if value:
            config[key] = value

    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            raw = f.read().strip()
            if raw:
                if not raw.lstrip().startswith('{'):
                    raw = '{' + raw
                if not raw.rstrip().endswith('}'):
                    raw = raw + '}'
                try:
                    file_config = json.loads(raw)
                    if isinstance(file_config, dict):
                        config.update(file_config)
                except json.JSONDecodeError:
                    pass
    return config

CONFIG = load_config()

ALPACA_KEY = CONFIG.get('ALPACA_KEY')
ALPACA_SECRET = CONFIG.get('ALPACA_SECRET')
ALPHA_VANTAGE_KEY = CONFIG.get('ALPHA_VANTAGE_KEY')
PUSHBULLET_TOKEN = CONFIG.get('PUSHBULLET_TOKEN')
USER_EMAIL = CONFIG.get('USER_EMAIL')
STRIPE_SECRET_KEY = CONFIG.get('STRIPE_SECRET_KEY')
