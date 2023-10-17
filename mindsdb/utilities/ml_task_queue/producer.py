import pickle

from redis.exceptions import ConnectionError
from walrus import Database
from pandas import DataFrame

from mindsdb.utilities.context import context as ctx
from mindsdb.utilities.config import Config
from mindsdb.utilities.ml_task_queue.utils import RedisKey, to_bytes
from mindsdb.utilities.ml_task_queue.task import Task
from mindsdb.utilities.ml_task_queue.const import (
    TASKS_STREAM_NAME,
    ML_TASK_TYPE,
    ML_TASK_STATUS
)


class MLTaskProducer:
    """ Interface around the redis for putting tasks to the queue

        Attributes:
            db (Redis): database object
            stream
            cache
            pubsub
    """

    def __init__(self) -> None:
        config = Config().get('ml_task_queue', {})
        self.db = Database(
            host=config.get('host', 'localhost'),
            port=config.get('port', 6379),
            db=config.get('db', 0),
            username=config.get('username'),
            password=config.get('password'),
            protocol=3
        )
        try:
            self.db.ping()
        except ConnectionError:
            print('Cant connect to redis')
            raise
        self.stream = self.db.Stream(TASKS_STREAM_NAME)
        self.cache = self.db.cache()
        self.pubsub = self.db.pubsub()

    def apply_async(self, task_type: ML_TASK_TYPE, model_id: int, payload: dict, dataframe: DataFrame = None) -> Task:
        ''' Add tasks to the queue

            Args:
                task_type (ML_TASK_TYPE): type of the task
                model_id (int): model identifier
                payload (dict): lightweight model data that will be added to stream message
                dataframe (DataFrame): dataframe will be transfered via regular redis storage

            Returns:
                Task: object representing the task
        '''
        try:
            payload = pickle.dumps(payload, protocol=5)
            redis_key = RedisKey.new()
            message = {
                "task_type": task_type.value,
                "company_id": '' if ctx.company_id is None else ctx.company_id,     # None can not be dumped
                "model_id": model_id,
                "payload": payload,
                "redis_key": redis_key.base
            }

            if dataframe is not None:
                self.cache.set(redis_key.dataframe, to_bytes(dataframe), 180)
            self.cache.set(redis_key.status, ML_TASK_STATUS.WAITING, 180)

            self.stream.add(message)
            return Task(self.db, redis_key)
        except ConnectionError:
            print('Cant send message to redis: connect failed')
            raise
