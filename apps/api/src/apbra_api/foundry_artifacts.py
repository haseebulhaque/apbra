"""Receipt-bound generated-file GETs. No model URLs, execution, discovery or retries."""

import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx

from .artifacts import MAX_ARTIFACT_BYTES
from .domain import ApplicationError
from .model_provider import FoundryAccess, FoundryBearer, ProviderProfile


class ArtifactTransportUnavailable(ApplicationError):
    status_code = 502
    code = 'OUTPUT_FILE_RETRIEVAL_UNAVAILABLE'
    public_message = ('The generated file could not be retrieved through the configured project. '
                      'The original response is retained. No analysis or design was retried.')


class ArtifactConnectionChanged(ApplicationError):
    status_code = 409
    code = 'OUTPUT_CONNECTION_CHANGED'
    public_message = ('The connection configuration changed. The original response is retained; '
                      'no output was saved.')


@dataclass(frozen=True)
class GeneratedFile:
    container_id: str
    file_id: str
    filename: str

    @property
    def binding(self) -> str:
        return json.dumps([self.container_id, self.file_id, self.filename], separators=(',', ':'))


def generated_files(raw: bytes) -> tuple[GeneratedFile, ...]:
    """Only service annotation carriers; never parse IDs or links from model text."""
    try:
        envelope = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        return ()
    output = envelope.get('output') if isinstance(envelope, dict) else None
    if not isinstance(output, list):
        return ()
    result: list[GeneratedFile] = []
    for message in output:
        if (not isinstance(message, dict) or message.get('type') != 'message'
                or message.get('role') != 'assistant'):
            continue
        content = message.get('content')
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get('type') != 'output_text':
                continue
            annotations = part.get('annotations')
            if not isinstance(annotations, list):
                continue
            for annotation in annotations:
                if (not isinstance(annotation, dict)
                        or annotation.get('type') != 'container_file_citation'):
                    continue
                container, file, filename = (annotation.get(key) for key in
                                             ('container_id', 'file_id', 'filename'))
                if (not isinstance(container, str) or not isinstance(file, str)
                        or re.fullmatch(r'[A-Za-z0-9_-]{1,255}', container) is None
                        or re.fullmatch(r'[A-Za-z0-9_-]{1,255}', file) is None
                        or not isinstance(filename, str) or not filename):
                    continue
                try:
                    filename.encode('utf-8')
                except UnicodeEncodeError:
                    continue
                reference = GeneratedFile(container, file, filename)
                if reference not in result:
                    result.append(reference)
    return tuple(result)


def project_file_url(profile: ProviderProfile, reference: GeneratedFile) -> str:
    endpoint = urlsplit(profile.endpoint)
    match = re.fullmatch(
        r'(/api/projects/[^/]+)/agents/[^/]+/endpoint/protocols/openai/responses', endpoint.path
    )
    if (profile.protocol != 'FOUNDRY_AGENT_RESPONSES' or endpoint.scheme != 'https'
            or endpoint.username is not None or endpoint.password is not None
            or endpoint.query or endpoint.fragment or not match
            or any(re.fullmatch(r'[A-Za-z0-9_-]{1,255}', value) is None
                   for value in (reference.container_id, reference.file_id))):
        raise ArtifactTransportUnavailable()
    path = (match.group(1) + '/openai/v1/containers/' + reference.container_id
            + '/files/' + reference.file_id + '/content')
    return str(urlunsplit((endpoint.scheme, endpoint.netloc, path, '', '')))


def retrieve_file(
    profile: ProviderProfile, access: FoundryAccess, reference: GeneratedFile,
    ready: Callable[[], bool], *, transport: httpx.BaseTransport | None = None,
) -> bytes:
    """One bounded content GET using the existing qualified Entra lease; bytes stay opaque."""
    target = project_file_url(profile, reference)
    if (access.profile_id != profile.profile_id
            or access.configuration_id != profile.configuration_id
            or (profile.agent_version is not None and access.agent_version != profile.agent_version)
            or (transport is None and access.qualification != 'LIVE_METADATA_VERIFIED')):
        raise ArtifactTransportUnavailable()
    deadline = time.monotonic() + profile.time_budget_seconds
    try:
        if ready() is not True:
            raise ArtifactTransportUnavailable()
        bearer = access.credential()
        if (not isinstance(bearer, FoundryBearer) or not bearer.token
                or bearer.audience != 'https://ai.azure.com'
                or type(bearer.expires_at) not in {int, float}
                or not math.isfinite(bearer.expires_at)):
            raise ArtifactTransportUnavailable()

        def remaining() -> float:
            seconds = deadline - time.monotonic()
            if seconds <= 0 or bearer.expires_at <= time.time() + seconds or ready() is not True:
                raise ArtifactTransportUnavailable()
            return seconds

        timeout = min(profile.request_timeout_seconds, remaining())
        with httpx.Client(transport=transport, follow_redirects=False,
                          trust_env=False, timeout=timeout) as client, client.stream(
            'GET', target, headers={'Authorization': 'Bearer ' + bearer.token,
                                    'Accept': 'application/octet-stream',
                                    'Accept-Encoding': 'identity'},
        ) as response:
            if (response.status_code != 200
                    or response.headers.get('Content-Encoding', 'identity').strip().lower()
                    not in {'', 'identity'}):
                raise ArtifactTransportUnavailable()
            content = bytearray()
            for chunk in response.iter_raw():
                remaining()
                if len(content) + len(chunk) > MAX_ARTIFACT_BYTES:
                    raise ArtifactTransportUnavailable()
                content.extend(chunk)
            remaining()
            length = response.headers.get('Content-Length')
            if not content or (length is not None and (
                not length.isdecimal() or int(length) != len(content)
            )):
                raise ArtifactTransportUnavailable()
            return bytes(content)
    except Exception:
        # SDK/HTTP/provider messages and response bodies can contain credentials or private URLs.
        raise ArtifactTransportUnavailable() from None
