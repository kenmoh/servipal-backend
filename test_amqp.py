from kombu import Connection

broker_url = "amqp://servipal:%40Areneth86@140.238.74.129:5672/servipal"
print(f"Testing connection to {broker_url}...")
try:
    with Connection(broker_url) as conn:
        conn.connect()
        print("Successfully connected to RabbitMQ!")
except Exception as e:
    print(f"Failed to connect: {e}")
