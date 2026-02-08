from abc import ABC, abstractmethod

class Connector(ABC):

    @abstractmethod
    async def send_event(self, event: dict):
        pass

class Connector(ABC):
    @abstractmethod
    async def handle_event(self, event: dict):
        pass
