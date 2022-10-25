import random
import asyncio
import re
import time
import threading
from typing import Dict

from nonebot import on_message, require, get_bot, logger
from nonebot.exception import ActionFailed
from nonebot.typing import T_State
from nonebot.rule import keyword, to_me, Rule
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.adapters.onebot.v11 import permission
from nonebot.permission import Permission
from nonebot.permission import SUPERUSER
from src.common.config import BotConfig

from .model import Chat


def setup_any_message_handler(message_id_lock: threading.Lock, message_id_dict: Dict):
    '''配置任意消息处理器'''
    any_msg = on_message(
        priority=15,
        block=False,
        permission=permission.GROUP  # | permission.PRIVATE_FRIEND
    )

    @any_msg.handle()
    async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
        to_learn = True
        # 多账号登陆，且在同一群中时；避免一条消息被处理多次
        with message_id_lock:
            message_id = event.message_id
            group_id = event.group_id
            if group_id in message_id_dict:
                if message_id in message_id_dict[group_id]:
                    to_learn = False
            else:
                message_id_dict[group_id] = []

            group_message = message_id_dict[group_id]
            group_message.append(message_id)
            if len(group_message) > 100:
                group_message = group_message[:-10]

        chat: Chat = Chat(event)

        answers = None
        config = BotConfig(event.self_id, event.group_id)
        if config.is_cooldown('repeat'):
            answers = chat.answer()

        if to_learn:
            chat.learn()

        if not answers:
            return

        config.refresh_cooldown('repeat')
        delay = random.randint(2, 5)
        for item in answers:
            logger.info(
                'repeater | bot [{}] ready to send [{}] to group [{}]'.format(event.self_id, item, event.group_id))

            await asyncio.sleep(delay)
            config.refresh_cooldown('repeat')
            try:
                await any_msg.send(item)
            except ActionFailed:
                if not BotConfig(event.self_id).security():
                    continue

                # 自动删除失效消息。若 bot 处于风控期，请勿开启该功能
                shutup = await is_shutup(event.self_id, event.group_id)
                if not shutup:  # 说明这条消息失效了
                    logger.info('repeater | bot [{}] ready to ban [{}] in group [{}]'.format(
                        event.self_id, str(item), event.group_id))
                    Chat.ban(event.group_id, event.self_id,
                             str(item), 'ActionFailed')
                    break
            delay = random.randint(1, 3)


def setup_banning_message_handler(is_admin: bool):
    '''配置禁止发送消息处理器'''
    ban_msg = on_message(
        rule=to_me() & keyword('不可以') & Rule(is_reply),
        priority=5,
        block=True,
        permission=is_admin
    )

    @ban_msg.handle()
    async def _(bot: Bot, event: GroupMessageEvent, state: T_State):

        if '[CQ:reply,' not in event.raw_message:
            return False

        raw_message = ''
        for item in event.reply.message:
            raw_reply = str(item)
            # 去掉图片消息中的 url, subType 等字段
            raw_message += re.sub(r'(\[CQ\:.+)(?:,url=*)(\])',
                                  r'\1\2', raw_reply)

        logger.info('repeater | bot [{}] ready to ban [{}] in group [{}]'.format(
            event.self_id, raw_message, event.group_id))

        Chat.ban(event.group_id, event.self_id, raw_message, str(event.user_id))


def setup_banning_latest_message_handler(is_admin: bool):
    '''配置禁止发送最近一条消息处理器'''
    ban_msg_latest = on_message(
        rule=to_me() & Rule(is_banning_message),
        priority=5,
        block=True,
        permission=is_admin
    )

    @ban_msg_latest.handle()
    async def _(bot: Bot, event: GroupMessageEvent, state: T_State):
        logger.info(
            'repeater | bot [{}] ready to ban latest reply in group [{}]'.format(
                event.self_id, event.group_id))

        Chat.ban(event.group_id, event.self_id, '', str(event.user_id))


def setup_active_speaking_handler():
    '''配置主动说话处理器'''
    speak_sched = require('nonebot_plugin_apscheduler').scheduler

    @speak_sched.scheduled_job('interval', seconds=5)
    async def _():

        ret = Chat.speak()
        if not ret:
            return

        bot_id, group_id, messages = ret

        for msg in messages:
            logger.info(
                'repeater | bot [{}] ready to speak [{}] to group [{}]'.format(
                    bot_id, msg, group_id))
            await get_bot(str(bot_id)).call_api('send_group_msg', **{
                'message': msg,
                'group_id': group_id
            })
            await asyncio.sleep(random.randint(2, 5))


def setup_removing_outdated_messages_handler():
    '''配置删除过期消息处理器'''
    update_sched = require('nonebot_plugin_apscheduler').scheduler

    @update_sched.scheduled_job('cron', hour='4')
    def _():
        Chat.clearup_context()


async def is_shutup(self_id: int, group_id: int) -> bool:
    info = await get_bot(str(self_id)).call_api('get_group_member_info', **{
        'user_id': self_id,
        'group_id': group_id
    })
    flag: bool = info['shut_up_timestamp'] > time.time()

    logger.info('repeater | bot [{}] in group [{}] is shutup: {}'.format(
        self_id, group_id, flag))

    return flag


async def is_config_admin(event: GroupMessageEvent) -> bool:
    '''判断在配置中是否为管理员'''
    return BotConfig(event.self_id).is_admin(event.user_id)


async def is_reply(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    '''判断是否为回复消息'''
    return bool(event.reply)


async def is_banning_message(bot: Bot, event: GroupMessageEvent, state: T_State) -> bool:
    '''判断是否为禁止发送消息'''
    return event.get_plaintext().strip() == '不可以发这个'


def setup():
    '''配置消息处理器'''
    message_id_lock = threading.Lock()
    message_id_dict = {}

    is_admin = permission.GROUP_OWNER | permission.GROUP_ADMIN | SUPERUSER | Permission(
        is_config_admin)

    setup_any_message_handler(message_id_lock, message_id_dict)
    setup_banning_message_handler(is_admin)
    setup_banning_latest_message_handler(is_admin)
    setup_active_speaking_handler()
    setup_removing_outdated_messages_handler()


setup()
