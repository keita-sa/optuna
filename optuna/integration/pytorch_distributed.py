from datetime import datetime
import pickle
from typing import Any
from typing import Callable
from typing import Dict
from typing import Optional
from typing import Sequence

import optuna
from optuna._experimental import experimental
from optuna._imports import try_import
from optuna.distributions import BaseDistribution
from optuna.distributions import CategoricalChoiceType


with try_import() as _imports:
    import torch
    import torch.distributed as dist


@experimental("2.6.0")
class TorchDistributedTrial(optuna.trial.BaseTrial):
    """A wrapper of :class:`~optuna.trial.Trial` to incorporate Optuna with PyTorch distributed.

    .. seealso::
        :class:`~optuna.integration.TorchDistributedTrial` provides the same interface as
        :class:`~optuna.trial.Trial`. Please refer to :class:`optuna.trial.Trial` for further
        details.

    See `the example <https://github.com/optuna/optuna/blob/master/
    examples/pytorch_distributed_simple.py>`__
    if you want to optimize an objective function that trains neural network
    written with PyTorch distributed data parallel.

    Args:
        trial:
            A :class:`~optuna.trial.Trial` object or :obj:`None`. Please set trial object in
            rank-0 node and set :obj:`None` in the other rank node.
    """

    def __init__(self, trial: Optional[optuna.trial.Trial]) -> None:

        _imports.check()
        self._delegate = trial

    def suggest_float(
        self,
        name: str,
        low: float,
        high: float,
        *,
        step: Optional[float] = None,
        log: bool = False,
    ) -> float:
        def func() -> float:

            assert self._delegate is not None
            return self._delegate.suggest_float(name, low, high, step=step, log=log)

        return _call_and_communicate(func, torch.float)

    def suggest_uniform(self, name: str, low: float, high: float) -> float:
        def func() -> float:

            assert self._delegate is not None
            return self._delegate.suggest_uniform(name, low, high)

        return _call_and_communicate(func, torch.float)

    def suggest_loguniform(self, name: str, low: float, high: float) -> float:
        def func() -> float:

            assert self._delegate is not None
            return self._delegate.suggest_loguniform(name, low, high)

        return _call_and_communicate(func, torch.float)

    def suggest_discrete_uniform(self, name: str, low: float, high: float, q: float) -> float:
        def func() -> float:

            assert self._delegate is not None
            return self._delegate.suggest_discrete_uniform(name, low, high, q=q)

        return _call_and_communicate(func, torch.float)

    def suggest_int(self, name: str, low: int, high: int, step: int = 1, log: bool = False) -> int:
        def func() -> float:

            assert self._delegate is not None
            return self._delegate.suggest_int(name, low, high, step=step, log=log)

        return _call_and_communicate(func, torch.int)

    def suggest_categorical(self, name: str, choices: Sequence["CategoricalChoiceType"]) -> Any:
        def func() -> CategoricalChoiceType:

            assert self._delegate is not None
            return self._delegate.suggest_categorical(name, choices)

        return _call_and_communicate_obj(func)

    def report(self, value: float, step: int) -> None:

        if dist.get_rank() == 0:
            assert self._delegate is not None
            self._delegate.report(value, step)
        dist.barrier()

    def should_prune(self) -> bool:
        def func() -> bool:

            assert self._delegate is not None
            # Some pruners return numpy.bool_, which is incompatible with bool.
            return bool(self._delegate.should_prune())

        # torch.bool seems to be the correct type, but the communication fails
        # due to the RuntimeError.
        return _call_and_communicate(func, torch.uint8)

    def set_user_attr(self, key: str, value: Any) -> None:

        if dist.get_rank() == 0:
            assert self._delegate is not None
            self._delegate.set_user_attr(key, value)
        dist.barrier()

    def set_system_attr(self, key: str, value: Any) -> None:

        if dist.get_rank() == 0:
            assert self._delegate is not None
            self._delegate.set_system_attr(key, value)
        dist.barrier()

    @property
    def number(self) -> int:
        def func() -> int:

            assert self._delegate is not None
            return self._delegate.number

        return _call_and_communicate(func, torch.int)

    @property
    def params(self) -> Dict[str, Any]:
        def func() -> Dict[str, Any]:

            assert self._delegate is not None
            return self._delegate.params

        return _call_and_communicate_obj(func)

    @property
    def distributions(self) -> Dict[str, BaseDistribution]:
        def func() -> Dict[str, BaseDistribution]:

            assert self._delegate is not None
            return self._delegate.distributions

        return _call_and_communicate_obj(func)

    @property
    def user_attrs(self) -> Dict[str, Any]:
        def func() -> Dict[str, Any]:

            assert self._delegate is not None
            return self._delegate.user_attrs

        return _call_and_communicate_obj(func)

    @property
    def system_attrs(self) -> Dict[str, Any]:
        def func() -> Dict[str, Any]:

            assert self._delegate is not None
            return self._delegate.system_attrs

        return _call_and_communicate_obj(func)

    @property
    def datetime_start(self) -> Optional[datetime]:
        def func() -> Optional[datetime]:

            assert self._delegate is not None
            return self._delegate.datetime_start

        return _call_and_communicate_obj(func)


def _call_and_communicate(func: Callable, dtype: "torch.dtype") -> Any:
    buffer = torch.empty(1, dtype=dtype)
    rank = dist.get_rank()
    if rank == 0:
        result = func()
        buffer[0] = result
    if dist.get_backend() == "nccl":
        buffer = buffer.cuda(torch.device(rank))
    dist.broadcast(buffer, src=0)
    return buffer.item()


def _call_and_communicate_obj(func: Callable) -> Any:
    buffer = None
    size_buffer = torch.empty(1, dtype=torch.int)
    rank = dist.get_rank()
    if rank == 0:
        result = func()
        buffer = _to_tensor(result)
        size_buffer[0] = buffer.shape[0]
    if dist.get_backend() == "nccl":
        size_buffer = size_buffer.cuda(torch.device(rank))
    dist.broadcast(size_buffer, src=0)
    buffer_size = int(size_buffer.item())
    if rank != 0:
        buffer = torch.empty(buffer_size, dtype=torch.uint8)
    assert buffer is not None
    if dist.get_backend() == "nccl":
        buffer = buffer.cuda(torch.device(rank))
    dist.broadcast(buffer, src=0)
    return _from_tensor(buffer)


def _to_tensor(obj: Any) -> "torch.Tensor":
    b = bytearray(pickle.dumps(obj))
    return torch.tensor(b, dtype=torch.uint8)


def _from_tensor(tensor: "torch.Tensor") -> Any:
    b = bytearray(tensor.tolist())
    return pickle.loads(b)
