from functools import lru_cache

from app.application.automation.pipeline import AutomationPipelineService
from app.application.automation.history_service import AutomationHistoryService
from app.application.automation.config_service import AutomationConfigService
from app.application.automation.llm_queue_service import LlmQueueService
from app.application.automation.order_queue_service import OrderQueueService
from app.application.automation.prompt_pipeline_worker import PromptPipelineWorker
from app.application.automation.llm_queue_worker import LlmQueueWorker
from app.application.automation.order_queue_worker import OrderQueueWorker
from app.application.bus.outbox_service import OutboxService
from app.application.prompt_builder.dependencies import get_prompt_builder_service
from app.application.llm_pipeline.dependencies import get_llm_execution_service
from app.application.trade_executor.dependencies import get_trade_executor_service
from app.application.trade_guard.dependencies import get_trade_guard_service
from app.application.circuit_breaker.dependencies import get_circuit_breaker_service
from app.application.ema_scanner.dependencies import get_ema_config_service, get_ema_scanner_service
from app.application.ema_state_manager.dependencies import get_ema_state_manager_service
from app.application.prompt_builder.queue_service import PromptBuildQueueService
from app.application.quant_scanner.dependencies import get_quant_config_service, get_quant_scanner_service
from app.application.portfolio.dependencies import get_portfolio_service
from app.application.telegram.dependencies import get_telegram_notification_service
from app.infrastructure.bus.outbox_repository import OutboxRepository
from app.infrastructure.crypto.cipher import get_credentials_cipher
from app.infrastructure.db import get_sessionmaker
from app.infrastructure.repositories.prompt_build_queue_repository import PromptBuildQueueRepository
from app.infrastructure.repositories.llm_queue_repository import LlmQueueRepository
from app.infrastructure.repositories.order_queue_repository import OrderQueueRepository
from app.infrastructure.repositories.automation_config_repository import SqlAutomationConfigRepository
from app.infrastructure.repositories.ai_provider_repository import SqlProviderConfigRepository
from app.infrastructure.repositories.automation_session_repository import SqlAutomationSessionRepository
from app.infrastructure.repositories.automation_log_repository import SqlAutomationLogRepository
from app.infrastructure.repositories.automation_trade_repository import SqlAutomationTradeRepository


@lru_cache(maxsize=1)
def get_outbox_service() -> OutboxService:
    history_service = get_automation_history_service()
    return OutboxService(
        OutboxRepository(get_sessionmaker()),
        history_recorder=history_service.record_event,
    )


@lru_cache(maxsize=1)
def get_automation_history_service() -> AutomationHistoryService:
    session_repo = SqlAutomationSessionRepository(get_sessionmaker())
    log_repo = SqlAutomationLogRepository(get_sessionmaker())
    trade_repo = SqlAutomationTradeRepository(get_sessionmaker())
    return AutomationHistoryService(
        session_repo=session_repo,
        log_repo=log_repo,
        trade_repo=trade_repo,
    )


@lru_cache(maxsize=1)
def get_prompt_queue_service() -> PromptBuildQueueService:
    repository = PromptBuildQueueRepository(get_sessionmaker())
    return PromptBuildQueueService(repository)


@lru_cache(maxsize=1)
def get_llm_queue_service() -> LlmQueueService:
    repository = LlmQueueRepository(get_sessionmaker())
    return LlmQueueService(repository)


@lru_cache(maxsize=1)
def get_order_queue_service() -> OrderQueueService:
    repository = OrderQueueRepository(get_sessionmaker())
    return OrderQueueService(repository)


@lru_cache(maxsize=1)
def get_automation_config_service() -> AutomationConfigService:
    repository = SqlAutomationConfigRepository(get_sessionmaker())
    return AutomationConfigService(repository)


@lru_cache(maxsize=1)
def get_automation_pipeline_service() -> AutomationPipelineService:
    return AutomationPipelineService(
        ema_scanner=get_ema_scanner_service(),
        ema_config=get_ema_config_service(),
        ema_state_manager=get_ema_state_manager_service(),
        quant_scanner=get_quant_scanner_service(),
        quant_config=get_quant_config_service(),
        prompt_queue=get_prompt_queue_service(),
        outbox=get_outbox_service(),
        portfolio_service=get_portfolio_service(),
        telegram_notifier=get_telegram_notification_service(),
        history_service=get_automation_history_service(),
    )


@lru_cache(maxsize=1)
def get_prompt_pipeline_worker() -> PromptPipelineWorker:
    repository = PromptBuildQueueRepository(get_sessionmaker())
    return PromptPipelineWorker(
        repository=repository,
        prompt_builder=get_prompt_builder_service(),
        llm_queue=get_llm_queue_service(),
        outbox=get_outbox_service(),
    )


@lru_cache(maxsize=1)
def get_llm_queue_worker() -> LlmQueueWorker:
    repository = LlmQueueRepository(get_sessionmaker())
    provider_repository = SqlProviderConfigRepository(
        get_sessionmaker(),
        cipher=get_credentials_cipher(),
    )
    return LlmQueueWorker(
        repository=repository,
        llm_pipeline=get_llm_execution_service(),
        order_queue=get_order_queue_service(),
        outbox=get_outbox_service(),
        provider_repository=provider_repository,
        automation_config_service=get_automation_config_service(),
        telegram_notifier=get_telegram_notification_service(),
    )


@lru_cache(maxsize=1)
def get_order_queue_worker() -> OrderQueueWorker:
    repository = OrderQueueRepository(get_sessionmaker())
    return OrderQueueWorker(
        repository=repository,
        trade_guard=get_trade_guard_service(),
        circuit_breaker=get_circuit_breaker_service(),
        trade_executor=get_trade_executor_service(),
        outbox=get_outbox_service(),
        portfolio_service=get_portfolio_service(),
    )
