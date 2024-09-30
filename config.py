import json

def load(config_file='config.json'):
    with open(config_file, 'r') as f:
        config = json.load(f)
    return config