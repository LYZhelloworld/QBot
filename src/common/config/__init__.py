import pymongo
import time
from pymongo.collection import Collection
from collections import defaultdict
from abc import ABC
from typing import Any, Optional


class Config(ABC):
    _config_mongo: Optional[Collection] = None
    _table: Optional[str] = None
    _key: Optional[str] = None

    @classmethod
    def _get_config_mongo(cls) -> Collection:
        if cls._config_mongo is None:
            mongo_client = pymongo.MongoClient('127.0.0.1', 27017, w=0)
            mongo_db = mongo_client['QBot']
            cls._config_mongo = mongo_db[cls._table]
            cls._config_mongo.create_index(name='{}_index'.format(cls._key),
                                           keys=[(cls._key, pymongo.HASHED)])
        return cls._config_mongo

    _mongo_find_key: Optional[dict] = None
    _key_id: Optional[int] = None
    _cache: Optional[dict] = None

    @classmethod
    def _find_key(cls, key: str) -> Any:
        if cls._key_id not in cls._cache:
            # print("refresh config from mongodb")
            info = cls._get_config_mongo().find_one(cls._mongo_find_key)
            cls._cache[cls._key_id] = info

        if cls._key_id in cls._cache:
            key_cache = cls._cache[cls._key_id]
            if key_cache and key in key_cache:
                return key_cache[key]

        return None

    def __init__(self, table: str, key: str, key_id: int) -> None:
        self.__class__._table = table
        self.__class__._key = key
        self.__class__._key_id = key_id
        self.__class__._mongo_find_key = {key: key_id}
        self.__class__._cache = {}


class BotConfig(Config):
    def __init__(self, bot_id: int, group_id: int = 0, cooldown: int = 5) -> None:
        super().__init__(
            table='config',
            key='account',
            key_id=bot_id)

        self.bot_id = bot_id
        self.group_id = group_id
        self.cooldown = cooldown

    def security(self) -> bool:
        '''
        账号是否安全（不处于风控等异常状态）
        '''
        return bool(self._find_key('security'))

    def auto_accept(self) -> bool:
        '''
        是否自动接受加群、加好友请求
        '''
        return bool(self._find_key('auto_accept'))

    def is_admin(self, user_id: int) -> bool:
        '''
        是否是管理员
        '''
        admins = self._find_key('admins')
        return user_id in admins if admins else False

    def add_admin(self, user_id: int) -> None:
        '''
        添加管理员
        '''
        self._get_config_mongo().update_one(
            self._mongo_find_key,
            {'$push': {'admins': user_id}},
            upsert=True
        )

    _cooldown_data = {}

    def is_cooldown(self, action_type: str) -> bool:
        '''
        是否冷却完成
        '''
        if self.bot_id not in BotConfig._cooldown_data:
            return True

        if self.group_id not in BotConfig._cooldown_data[self.bot_id]:
            return True

        if action_type not in BotConfig._cooldown_data[self.bot_id][self.group_id]:
            return True

        cd = BotConfig._cooldown_data[self.bot_id][self.group_id][action_type]
        return cd + self.cooldown < time.time()

    def refresh_cooldown(self, action_type: str) -> None:
        '''
        刷新冷却时间
        '''
        if self.bot_id not in BotConfig._cooldown_data:
            BotConfig._cooldown_data[self.bot_id] = {}

        if self.group_id not in BotConfig._cooldown_data[self.bot_id]:
            BotConfig._cooldown_data[self.bot_id][self.group_id] = {}

        BotConfig._cooldown_data[self.bot_id][self.group_id][action_type] = time.time(
        )


class GroupConfig(Config):
    def __init__(self, group_id: int, cooldown: int = 5) -> None:
        super().__init__(
            table='group_config',
            key='group_id',
            key_id=group_id)

        self.group_id = group_id
        self.cooldown = cooldown

    _ban_cache = {}

    def ban(self) -> None:
        '''
        拉黑该群
        '''
        GroupConfig._ban_cache[self.group_id] = True

        self._get_config_mongo().update_one(
            self._mongo_find_key,
            {'$set': {'banned': True}},
            upsert=True
        )

    def is_banned(self) -> bool:
        '''
        群是否被拉黑
        '''
        if self.group_id not in GroupConfig._ban_cache:
            banned = self._find_key('banned')
            GroupConfig._ban_cache[self.group_id] = True if banned else False

        return GroupConfig._ban_cache[self.group_id]

    _cooldown_data = {}

    def is_cooldown(self, action_type: str) -> bool:
        '''
        是否冷却完成
        '''
        if self.group_id not in GroupConfig._cooldown_data:
            return True

        if action_type not in GroupConfig._cooldown_data[self.group_id]:
            return True

        cd = GroupConfig._cooldown_data[self.group_id][action_type]
        return cd + self.cooldown < time.time()

    def refresh_cooldown(self, action_type: str) -> None:
        '''
        刷新冷却时间
        '''
        if self.group_id not in GroupConfig._cooldown_data:
            GroupConfig._cooldown_data[self.group_id] = {}

        GroupConfig._cooldown_data[self.group_id][action_type] = time.time()


class UserConfig(Config):
    def __init__(self, user_id: int) -> None:
        super().__init__(
            table='user_config',
            key='user_id',
            key_id=user_id)

        self.user_id = user_id

    _ban_cache = {}

    def ban(self) -> None:
        '''
        拉黑这个人
        '''
        UserConfig._ban_cache[self.user_id] = True

        self._get_config_mongo().update_one(
            self._mongo_find_key,
            {'$set': {'banned': True}},
            upsert=True
        )

    def is_banned(self) -> bool:
        '''
        是否被拉黑
        '''
        if self.user_id not in UserConfig._ban_cache:
            banned = self._find_key('banned')
            UserConfig._ban_cache[self.user_id] = True if banned else False

        return UserConfig._ban_cache[self.user_id]
