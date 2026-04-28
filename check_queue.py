import requests

url = "http://140.238.74.129:15672/api/queues/servipal/payment_order_creation"
auth = ("servipal", "@Areneth86")

response = requests.get(url, auth=auth)
if response.status_code == 200:
    data = response.json()
    print(f"Queue: {data.get('name')}")
    print(f"Messages Ready: {data.get('messages_ready')}")
    print(f"Messages Unacknowledged: {data.get('messages_unacknowledged')}")
    print(f"Total Messages: {data.get('messages')}")
    print(f"Consumers: {data.get('consumers')}")
else:
    print(f"Failed to fetch queue stats: {response.status_code} {response.text}")
