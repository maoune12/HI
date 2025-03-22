import os
import asyncio
import random
from telethon import TelegramClient, events
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.functions.messages import GetMessageReactionsListRequest
from telethon.errors import FloodWaitError, UserPrivacyRestrictedError, ChatAdminRequiredError

# Get credentials and channel info from environment variables
api_id = int(os.environ.get('API_ID'))
api_hash = os.environ.get('API_HASH')
phone_number = os.environ.get('PHONE_NUMBER')
source_channel = os.environ.get('SOURCE_CHANNEL')
target_channel = os.environ.get('TARGET_CHANNEL')

# Specify the number of old messages to process
OLD_MESSAGES_LIMIT = 100

# Increase delays to reduce request frequency (in seconds)
REQUEST_DELAY_MIN = 15
REQUEST_DELAY_MAX = 30

client = TelegramClient("session_name", api_id, api_hash)

async def process_reactors(message, target_entity, source_entity):
    """
    Fetch reactors of the message using GetMessageReactionsListRequest
    and invite them.
    """
    print(f"DEBUG: Fetching reactors for message id {message.id}")
    try:
        result = await client(GetMessageReactionsListRequest(
            peer=source_entity,
            msg_id=message.id,
            reaction='',  # empty means all reactions; adjust if needed
            offset=0,
            limit=100,
        ))
    except Exception as e:
        print(f"DEBUG: Error fetching reactions for message id {message.id}: {e}")
        return

    if not result.users:
        print(f"DEBUG: No reactors found for message id {message.id}")
        return

    for user in result.users:
        if not user.username:
            print(f"DEBUG: Reactor {user.id} has no username; skipping")
            continue
        try:
            print(f"DEBUG: Inviting reactor {user.username}")
            await client(InviteToChannelRequest(target_entity, [user.username]))
            print(f"SUCCESS: Invited reactor {user.username}")
        except FloodWaitError as e:
            print(f"DEBUG: Flood wait for reactor; sleeping for {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
        except UserPrivacyRestrictedError:
            print(f"DEBUG: Reactor {user.username} has privacy restrictions; skipping")
        except Exception as e:
            print(f"DEBUG: Error inviting reactor {user.username}: {e}")
        # Increased delay between invites to reduce frequency
        await asyncio.sleep(random.randint(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

async def process_message(message, target_entity, source_entity):
    """Process a single message: invite the sender (if available) and process reactors."""
    print(f"DEBUG: Processing message with id {message.id}")

    # Process sender if available
    if message.from_id:
        try:
            user_id = message.from_id.user_id if hasattr(message.from_id, 'user_id') else int(message.from_id)
        except Exception as e:
            print(f"DEBUG: Error extracting user_id: {e}")
            user_id = None

        if user_id:
            try:
                user_entity = await client.get_entity(user_id)
            except Exception as e:
                print(f"DEBUG: Error getting entity for user_id {user_id}: {e}")
                user_entity = None

            if user_entity and user_entity.username:
                try:
                    print(f"DEBUG: Inviting user {user_entity.username}")
                    await client(InviteToChannelRequest(target_entity, [user_entity.username]))
                    print(f"SUCCESS: Invited {user_entity.username}")
                except FloodWaitError as e:
                    print(f"DEBUG: Flood wait encountered for user; sleeping for {e.seconds} seconds")
                    await asyncio.sleep(e.seconds)
                except UserPrivacyRestrictedError:
                    print(f"DEBUG: User {user_entity.username} has privacy restrictions; skipping")
                except Exception as e:
                    print(f"DEBUG: Error inviting user {user_entity.username}: {e}")
                await asyncio.sleep(random.randint(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))
            else:
                print("DEBUG: User entity not found or has no username; skipping sender invite")
        else:
            print("DEBUG: Could not extract user_id from message")
    else:
        print("DEBUG: Message has no from_id; skipping sender invite")

    # Process reactors for the message
    await process_reactors(message, target_entity, source_entity)

async def main():
    await client.start(phone=phone_number)
    print("Logged in successfully!")

    # Get channel entities
    source_entity = await client.get_entity(source_channel)
    target_entity = await client.get_entity(target_channel)

    # Attempt to iterate participants directly (if possible)
    try:
        print("DEBUG: Attempting to iterate participants from the source channel")
        async for user in client.iter_participants(source_entity):
            if not user.username:
                print(f"DEBUG: Skipping user {user.id} with no username")
                continue
            try:
                print(f"DEBUG: Inviting participant {user.username}")
                await client(InviteToChannelRequest(target_entity, [user.username]))
                print(f"SUCCESS: Invited {user.username}")
            except FloodWaitError as e:
                print(f"DEBUG: Flood wait: sleeping for {e.seconds} seconds")
                await asyncio.sleep(e.seconds)
            except UserPrivacyRestrictedError:
                print(f"DEBUG: User {user.username} has privacy restrictions; skipping")
            except Exception as e:
                print(f"DEBUG: Error inviting {user.username}: {e}")
            await asyncio.sleep(random.randint(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))
    except ChatAdminRequiredError:
        print("DEBUG: Cannot fetch participants directly due to channel restrictions; switching to message processing.")

    # Process old messages first
    print(f"DEBUG: Processing the last {OLD_MESSAGES_LIMIT} old messages from the source channel")
    try:
        async for message in client.iter_messages(source_entity, limit=OLD_MESSAGES_LIMIT):
            await process_message(message, target_entity, source_entity)
    except Exception as e:
        print(f"DEBUG: Error while processing old messages: {e}")

    # Register an event handler for new messages in the source channel
    @client.on(events.NewMessage(chats=source_entity))
    async def new_message_handler(event):
        message = event.message
        print(f"DEBUG: New message received with id {message.id}")
        await process_message(message, target_entity, source_entity)

    print("DEBUG: Listening for new messages...")
    await client.run_until_disconnected()

with client:
    client.loop.run_until_complete(main())
