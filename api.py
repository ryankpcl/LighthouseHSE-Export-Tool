import config
import requests
import sys

#Load settings file
settings = config.load()
headers = "{'RpmApiKey': settings['cube_api'], 'Content-Type': 'application/json'}"

def headers():
    global settings
    
    return {
        'RpmApiKey': settings['cube_api'],
        'Content-Type': 'application/json'
    }

# Function to fetch data from API
def fetch_data(url, data=None):   
    try:
        api_headers = headers()  # Call the headers function to get the dictionary
        response = requests.post(url, headers=api_headers, json=data)
        
        response.raise_for_status()  # Raises an error for bad status codes
    except:
        print ("Error fetching data from Cube API...")
        sys.exit(1)
        
    return response.json()

# Function to fetch data from API
def fetch_form(form_id):
    try:
        payload = {
            "FormID": form_id
        }
        response = requests.post(settings['api_urls']['data'], headers=headers(), json=payload)
        response.raise_for_status()
        
    except:
        print(response)
        print (f"Error fetching form {form_id}")
        return None
        sys.exit(1)
        
    return response.json()

# Function to fetch file download URL from API
def fetch_file_url(file_id):
    payload = {
        "FileID": file_id,
        "ReturnDownloadUrl": True
    }
    response = requests.post(settings['api_urls']['files'], headers=headers(), json=payload)
    
    return response.json()["Result"]["DownloadUrl"]

def endpoints():
    global settings
    
    return settings['api_urls']
