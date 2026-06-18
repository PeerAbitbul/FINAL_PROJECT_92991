import datetime
import os
import requests
import time


def build_url(hour):
    base_url = os.environ.get('VENDOR_URL')
    filename = f"{hour.year}-{hour.month:02d}-{hour.day:02d}-{hour.hour}.json.gz"
    return f"{base_url}/{filename}"

def fetch_file(hour):
    url = build_url(hour)
    try:
        response = requests.get(url)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data for {hour}: {e}")
        time.sleep(10)
        return None
    
    response_status = response.status_code
    if response_status == 200:
        print(f"Successfully fetched data for {hour}")
    elif response_status == 404:
        print(f"No data available for {hour} (404 Not Found)")
        time.sleep(5)
        return None
    elif response_status == 503:
        print(f"Service unavailable for {hour} (503 Service Unavailable)")
        time.sleep(30)
        return None
    return response


