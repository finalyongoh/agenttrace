"""중앙 로깅 설정 모듈.

structlog 기반으로 JSON 구조화 로그를 생성합니다.
run_id 등 컨텍스트를 한 번 바인딩하면 이후 모든 로그에 자동 포함됩니다.

사용법:
    from agenttrace.logging_config import setup_logging, get_logger

    # 앱 기동 시 1회만 호출
    setup_logging()

    # 각 모듈에서
    logger = get_logger(__name__)
    log = logger.bind(run_id="abc123", node="collect_inputs")
    log.info("시작")
    log.info("완료", source_files=42, duration_ms=320)
"""
from __future__ import annotations

import logging
import sys
import time
from threading import Lock

import structlog


class StderrPrintLogger:
    """sys.stderr를 런타임에 동적으로 해석하여 출력하는 로그 출력기.
    pytest 등의 환경에서 sys.stderr 파일 객체가 테스트 간에 변경/교체되어도
    closed file 관련 ValueError가 발생하지 않도록 방지합니다.
    """
    _lock = Lock()

    def msg(self, message: str) -> None:
        with self._lock:
            sys.stderr.write(message + "\n")
            sys.stderr.flush()

    log = debug = info = warn = warning = error = critical = failure = msg


def setup_logging(level: str = "INFO") -> None:
    """전체 애플리케이션 로깅 초기화. 앱 기동 시 1회만 호출."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # stdlib logging 설정 (uvicorn, httpx 등 외부 라이브러리용)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=numeric_level,
    )

    # 외부 라이브러리 노이즈 억제
    for noisy in ("httpx", "openai", "langchain", "langgraph", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # structlog 프로세서 체인
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=lambda *args, **kwargs: StderrPrintLogger(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """모듈별 logger 반환."""
    return structlog.get_logger(name)


class NodeTimer:
    """노드 실행 시간 측정 컨텍스트 매니저.

    사용법:
        with NodeTimer(log, "collect_inputs") as t:
            # 노드 로직
            ...
        # 종료 시 자동으로 duration_ms 로그
    """

    def __init__(self, log: structlog.BoundLogger, node: str) -> None:
        self._log = log
        self._node = node
        self._start: float = 0.0

    def __enter__(self) -> "NodeTimer":
        self._start = time.perf_counter()
        self._log.info("시작", node=self._node)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        elapsed_ms = int((time.perf_counter() - self._start) * 1000)
        if exc_type:
            self._log.error("오류", node=self._node, duration_ms=elapsed_ms, error=str(exc_val))
        else:
            self._log.info("완료", node=self._node, duration_ms=elapsed_ms)
        return False
