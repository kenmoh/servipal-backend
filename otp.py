from app.utils.utils import send_otp


async def send_one_time_password():
    await send_otp(
        name="John Doe",
        email="johndoe@example.com",
        phone="09074345335"
    )

if __name__ == "__main__":
    import asyncio
    asyncio.run(send_one_time_password())