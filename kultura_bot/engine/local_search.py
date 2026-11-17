"""Request-scoped tool discovery for gateways without hosted tool search.

Accept only the caller's permission-filtered Toolset.defs. Search is an ordinary
function, not the provider's built-in tool_search. No provider/network calls here.
"""
import copy
import json
import re

from kultura_bot import settings

SEARCH_NAME = 'kultura_find_tools'
SEARCH = {
    'name': SEARCH_NAME,
    'description': 'Find tools by words or word stems in names, descriptions and parameters. '
                   'Words are alternatives. An empty query lists the entire permitted catalogue. '
                   'Pages contain up to 100 matches; use next_offset for the next page. Matching functions become available on the next step.',
    'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'offset': {'type': 'integer', 'minimum': 0}},
                   'required': ['query'], 'additionalProperties': False},
}


class Catalogue:
    def __init__(self, definitions):
        self._tools = {}
        self._loaded = set()
        self._recent = []
        self._always = set()
        for tool in definitions:
            if str(tool.get('type', '')).startswith('tool_search'):
                continue
            name = tool['name']
            if name in settings.HIDDEN_TOOLS:
                continue
            if name == SEARCH_NAME or name in self._tools:
                raise ValueError('Duplicate or reserved tool name')
            self._tools[name] = {
                'name': name, 'description': tool.get('description', ''),
                'parameters': copy.deepcopy(tool['input_schema']),
            }
            if not tool.get('defer_loading'):
                self._loaded.add(name)
                self._always.add(name)

    def search(self, query, offset=0):
        if not isinstance(query, str):
            raise ValueError('Search query must be a string')
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError('Invalid search offset')
        words = re.findall(r'\w+', query.casefold())
        matches = []
        for name, tool in self._tools.items():
            haystack = json.dumps(tool, ensure_ascii=False).casefold()
            if not words or any(word in haystack for word in words):
                matches.append({'name': name, 'description': tool['description']})
        page = matches[offset:offset + 100]
        self.load([t['name'] for t in page])
        return {'matches': page, 'count': len(matches), 'next_offset': offset + 100 if offset + 100 < len(matches) else None}

    def load(self, names):
        for name in names:
            if name in self._tools:
                if name in self._recent:
                    self._recent.remove(name)
                self._recent.append(name)
        self._recent = self._recent[-max(1, 127 - len(self._always)):]
        self._loaded = self._always | set(self._recent)

    def chat_tools(self):
        return [{'type': 'function', 'function': copy.deepcopy(tool)}
                for tool in [SEARCH, *(t for n, t in self._tools.items() if n in self._loaded)]]

    def can_call(self, name):
        return name in self._loaded
