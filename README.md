# Discord Music Bot

## Info
Based on the "basic_voice" discord.py example, expanded to add song queueing and improved performance.

## Commands
`!play <url>`  
`!skip`  
`!join [channel]`  
`!stop`  
`!clear`

## Setup
1. Create an application and bot in the Discord Developer Portal
2. Put the generated token in a .env file with the content `DISCORD_TOKEN=<token>`
3. Invite the bot to your server with the Discord Developer Portal URL generator -- add "bot" scope and "Send Messages", "Send Messages in Threads", "Connect", "Speak" and "Use Voice Activity" permissions
3. Run with `python3 ./main.py`
