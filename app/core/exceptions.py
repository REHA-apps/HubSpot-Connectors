from fastapi import HTTPException

class ConnectorException(HTTPException):
    pass