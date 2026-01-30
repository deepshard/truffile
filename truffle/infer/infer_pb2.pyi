from google.protobuf import empty_pb2 as _empty_pb2
from truffle.infer import irequest_pb2 as _irequest_pb2
from truffle.infer import iresponse_pb2 as _iresponse_pb2
from truffle.infer import model_pb2 as _model_pb2
from truffle.infer import embedding_pb2 as _embedding_pb2
from truffle.infer.convo import conversation_pb2 as _conversation_pb2
from truffle.infer.convo import msg_pb2 as _msg_pb2
from truffle.infer import tokenize_pb2 as _tokenize_pb2
from truffle.infer import gencfg_pb2 as _gencfg_pb2
from google.protobuf import descriptor as _descriptor
from typing import ClassVar as _ClassVar
from truffle.infer.irequest_pb2 import IRequest as IRequest
from truffle.infer.irequest_pb2 import BatchIRequest as BatchIRequest
from truffle.infer.irequest_pb2 import RequestPriority as RequestPriority
from truffle.infer.iresponse_pb2 import IResponse as IResponse
from truffle.infer.iresponse_pb2 import BatchIResponse as BatchIResponse
from truffle.infer.model_pb2 import EmbeddingModelInfo as EmbeddingModelInfo
from truffle.infer.model_pb2 import EmbeddingModelList as EmbeddingModelList
from truffle.infer.model_pb2 import ModelConfig as ModelConfig
from truffle.infer.model_pb2 import Model as Model
from truffle.infer.model_pb2 import ModelStateUpdate as ModelStateUpdate
from truffle.infer.model_pb2 import ModelList as ModelList
from truffle.infer.model_pb2 import GetModelRequest as GetModelRequest
from truffle.infer.model_pb2 import GetModelListRequest as GetModelListRequest
from truffle.infer.model_pb2 import SetModelsResponse as SetModelsResponse
from truffle.infer.model_pb2 import SetModelsRequest as SetModelsRequest
from truffle.infer.embedding_pb2 import Embeddable as Embeddable
from truffle.infer.embedding_pb2 import EmbeddingRequest as EmbeddingRequest
from truffle.infer.embedding_pb2 import EmbeddingResponse as EmbeddingResponse
from truffle.infer.convo.conversation_pb2 import Conversation as Conversation
from truffle.infer.convo.conversation_pb2 import BuiltContext as BuiltContext
from truffle.infer.tokenize_pb2 import TokenizeRequest as TokenizeRequest
from truffle.infer.tokenize_pb2 import TokenizeResponse as TokenizeResponse
from truffle.infer.gencfg_pb2 import ResponseFormat as ResponseFormat
from truffle.infer.gencfg_pb2 import GenerationConfig as GenerationConfig
from truffle.infer.gencfg_pb2 import ValidateConfigRequest as ValidateConfigRequest
from truffle.infer.gencfg_pb2 import ValidateConfigResponse as ValidateConfigResponse

DESCRIPTOR: _descriptor.FileDescriptor
REQUEST_PRIORITY_UNSPECIFIED: _irequest_pb2.RequestPriority
REQUEST_PRIORITY_LOW: _irequest_pb2.RequestPriority
REQUEST_PRIORITY_NORMAL: _irequest_pb2.RequestPriority
REQUEST_PRIORITY_REALTIME: _irequest_pb2.RequestPriority
