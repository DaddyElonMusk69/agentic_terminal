from typing import Any, Iterable, List


def normalize_topic(topic: Any) -> str:
    value = str(topic or "").strip()
    return value


def normalize_topics(data: Any) -> List[str]:
    raw: Iterable[Any]
    if isinstance(data, dict):
        raw = data.get("topics") or []
    elif isinstance(data, (list, tuple, set)):
        raw = data
    elif data is None:
        raw = []
    else:
        raw = [data]

    topics: List[str] = []
    for item in raw:
        value = normalize_topic(item)
        if not value or value in topics:
            continue
        topics.append(value)
    return topics


def topic_room(topic: str) -> str:
    normalized = normalize_topic(topic)
    return f"topic:{normalized}" if normalized else "topic:unknown"


def topic_rooms_for(topic: str) -> List[str]:
    normalized = normalize_topic(topic)
    if not normalized:
        return [topic_room(normalized)]

    parts = normalized.split(".")
    rooms = [topic_room(normalized)]

    for idx in range(len(parts) - 1, 0, -1):
        prefix = ".".join(parts[:idx])
        room = topic_room(f"{prefix}.*")
        if room not in rooms:
            rooms.append(room)

    return rooms
