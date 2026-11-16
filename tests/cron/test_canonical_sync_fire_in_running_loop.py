"""A sync canonical fire from inside a running loop must not book asyncio's own refusal.

A cron tick can fire while the gateway owner is unresolvable (draining for an update, or
restarting). When that caller already sits on a running event loop, ``asyncio.run(remote())``
refuses before any work starts; the broad handler then books that ``RuntimeError`` as the job's
failure instead of the honest "gateway unavailable" verdict. See the standalone delivery lane's
guard in ``cron/scheduler_delivery_standalone.py``.
"""
import asyncio
from contextlib import asynccontextmanager
import contextvars
import json

from cron import executions, jobs, scheduler_authority
from gateway import session_cron
from hermes_cli import gateway_client

PROFILE = contextvars.ContextVar('test_profile', default='default')


def peer(monkeypatch, call):
    class Peer:
        async def rpc(self, method, **params):
            return call(method, params)

    @asynccontextmanager
    async def connected():
        yield Peer()
    monkeypatch.setattr(gateway_client, 'connect_gateway', connected)


def test_running_loop_without_owner_still_runs_the_fire(tmp_path, monkeypatch):
    """No owner + a running loop runs the coroutine in a worker thread and returns its verdict."""
    with jobs.use_cron_store(tmp_path / 'cron'):
        job = jobs.create_job(prompt='report', schedule='every 1h', deliver='local')
        execution = executions.create_execution(job['id'], source='test')
        monkeypatch.setattr(session_cron, 'owner_for_home', lambda home: None)
        peer(monkeypatch, lambda method, params: (
            {'session_id': 's', 'admission_id': 'a'} if method == 'cron.submit'
            else {'status': 'terminal', 'job': job, 'result': [True, 'document', 'answer', None]}))

        async def fire():
            PROFILE.set('test-profile')
            return scheduler_authority.run_canonical_job(job, execution_id=execution['id'])

        assert asyncio.run(fire()) == (True, 'document', 'answer', None)
        journal = scheduler_authority.journal_path(job['id'], execution['id'])
        assert json.loads(journal.read_text())['receipt'] == {'session_id': 's', 'admission_id': 'a'}


def test_running_loop_without_owner_reports_the_gateway_not_asyncio(tmp_path, monkeypatch):
    """An unreachable gateway is the booked error, with the caller's ContextVars intact."""
    with jobs.use_cron_store(tmp_path / 'cron'):
        job = jobs.create_job(prompt='report', schedule='every 1h', deliver='local')
        monkeypatch.setattr(session_cron, 'owner_for_home', lambda home: None)

        def connect_gateway():
            # Reads the ContextVar in the thread that actually runs the coroutine: the profile
            # home override and secret scope live there, so a copied context must reach it.
            raise ConnectionRefusedError(f'gateway unavailable; profile={PROFILE.get()}')

        monkeypatch.setattr(gateway_client, 'connect_gateway', connect_gateway)

        async def fire():
            PROFILE.set('test-profile')
            return scheduler_authority.run_canonical_job(job)

        success, _output, _answer, error = asyncio.run(fire())
        assert success is False
        assert error == 'ConnectionRefusedError: gateway unavailable; profile=test-profile'
