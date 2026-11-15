"""
router.py: Легковесный и быстрый роутер запросов для BaseHTTPRequestHandler.
Обеспечивает декларативную регистрацию маршрутов, автоматический парсинг JSON/Query
и централизованную обработку ошибок.
"""

from dataclasses import dataclass, field
import json
from typing import Any, Callable, Dict, List, Optional
import urllib.parse


@dataclass
class RequestContext:
    """Контекст входящего HTTP-запроса."""
    handler: Any
    method: str
    path: str
    query_params: Dict[str, List[str]] = field(default_factory=dict)
    body: bytes = b""
    json_data: Optional[Dict[str, Any]] = None

    def get_query(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Возвращает строковое значение GET-параметра."""
        vals = self.query_params.get(key)
        return vals[0] if vals else default

    def get_json(self) -> Dict[str, Any]:
        """Возвращает распарсенный JSON тела запроса."""
        if self.json_data is not None:
            return self.json_data
        if not self.body:
            return {}
        try:
            self.json_data = json.loads(self.body.decode("utf-8"))
            return self.json_data
        except Exception:
            return {}


class Router:
    """Маршрутизатор HTTP-запросов."""

    def __init__(self):
        self._get_routes: Dict[str, Callable[[RequestContext], Any]] = {}
        self._post_routes: Dict[str, Callable[[RequestContext], Any]] = {}

    def get(self, path: str):
        """Декоратор регистрации GET-маршрута."""
        def decorator(func: Callable[[RequestContext], Any]):
            self._get_routes[path] = func
            return func
        return decorator

    def post(self, path: str):
        """Декоратор регистрации POST-маршрута."""
        def decorator(func: Callable[[RequestContext], Any]):
            self._post_routes[path] = func
            return func
        return decorator

    def dispatch(self, handler: Any, method: str) -> bool:
        """
        Диспетчеризирует запрос к зарегистрированному контроллеру.
        Возвращает True, если маршрут найден и обработан, иначе False.
        """
        parsed = urllib.parse.urlparse(handler.path)
        path = parsed.path
        routes = self._get_routes if method == "GET" else self._post_routes

        handler_func = routes.get(path)
        if not handler_func:
            return False

        # Формируем контекст
        body = b""
        if method == "POST":
            content_length = int(handler.headers.get("Content-Length", 0))
            if content_length > 0:
                body = handler.rfile.read(content_length)

        ctx = RequestContext(
            handler=handler,
            method=method,
            path=path,
            query_params=urllib.parse.parse_qs(parsed.query),
            body=body,
        )

        try:
            response = handler_func(ctx)
            if response is not None:
                self._send_response(handler, response)
        except Exception as e:
            import traceback
            traceback.print_exc()
            handler.send_error_json(str(e), status=500)

        return True

    def _send_response(self, handler: Any, response: Any):
        """Отправляет унифицированный ответ клиенту."""
        if isinstance(response, tuple):
            data, status = response
            handler.send_json(data, status=status)
        elif isinstance(response, (dict, list)):
            handler.send_json(response, status=200)
        elif isinstance(response, str):
            handler.send_response(200)
            handler.send_header("Content-Type", "text/plain; charset=utf-8")
            handler.send_header("Access-Control-Allow-Origin", "*")
            handler.end_headers()
            handler.wfile.write(response.encode("utf-8"))

