"""Terminal output decisions exercise the real persistent TCP device."""
import importlib

import pytest

from pickloop.device import DeviceClient, DeviceEmulator, DeviceError


@pytest.fixture
def resolve():
    assert importlib.util.find_spec('pickloop.stop_policy') is not None, 'terminal valve safety policy is missing'
    return importlib.import_module('pickloop.stop_policy').resolve_terminal_valve


@pytest.fixture
def rig(tmp_path):
    device=DeviceEmulator(journal_path=tmp_path/'device.sqlite').start()
    client=DeviceClient('127.0.0.1',device.port,timeout=.04)
    client.command(1,True)
    try:yield device,client
    finally:device.stop()


def test_detached_weak_vacuum_is_explicitly_switched_off_and_confirmed(resolve,rig):
    device,client=rig;device.set_feedback(-6.,False)
    report=resolve(client,'SEAL_NOT_CONFIRMED',1)
    assert report['action']=='OFF_CONFIRMED'
    assert report['status_before']['valve'] is True
    assert report['status']['valve'] is False
    assert report['status']['ack_id']==2
    assert report['command_id']==2
    assert report['next_command_id']==3
    assert client.status()['execution_count']==2
    # This helper neither advances physics nor invents pressure decay.
    assert client.status()['pressure_kpa']==-6.


@pytest.mark.parametrize('pressure,attached', [(-50.,True),(-6.,True),(-50.,False),(-10.,False),(10.,False)])
def test_attachment_or_nonweak_pressure_retains_output(resolve,rig,pressure,attached):
    device,client=rig;device.set_feedback(pressure,attached)
    report=resolve(client,'CANCELLED',1)
    assert report['action']=='RETAIN'
    assert report['command_id']==1
    assert report['next_command_id']==2
    assert client.status()['valve'] is True
    assert client.status()['execution_count']==1


@pytest.mark.parametrize('reason', ['DEVICE_UNCERTAIN','CANCELLED_DEVICE_UNCERTAIN','OUTPUT_UNCONFIRMED','HOLD_RECOVERY_REQUIRED'])
def test_uncertain_output_reason_never_issues_release_even_with_weak_feedback(resolve,rig,reason):
    device,client=rig;device.set_feedback(-6.,False)
    report=resolve(client,reason,1)
    assert report['action']=='RETAIN'
    assert client.status()['valve'] is True
    assert client.status()['execution_count']==1


def test_explicit_uncertainty_and_carrying_are_conservative_vetoes(resolve,rig):
    device,client=rig;device.set_feedback(-6.,False)
    assert resolve(client,'CANCELLED',1,output_uncertain=True)['action']=='RETAIN'
    assert resolve(client,'CANCELLED',1,carrying=True)['action']=='RETAIN'
    assert client.status()['execution_count']==1
    assert client.status()['valve'] is True


def test_successful_cancellation_fence_allows_off_only_when_unloaded(resolve,rig):
    device,client=rig;device.set_feedback(-6.,False)
    client.cancel(1)
    report=resolve(client,'CANCELLED',1)
    assert report['action']=='OFF_CONFIRMED'
    assert report['status']['ack_id']==2
    assert report['status']['cancelled'] is False


def test_carrying_cancel_keeps_current_cancelled_command_and_suction(resolve,rig):
    device,client=rig;device.set_feedback(-52.,True)
    client.cancel(1)
    report=resolve(client,'CANCELLED',1,carrying=True)
    assert report['action']=='RETAIN'
    status=client.status()
    assert status['valve'] is True
    assert status['cancelled'] is True
    assert status['execution_count']==1


def test_already_off_does_not_allocate_redundant_command(resolve,tmp_path):
    device=DeviceEmulator(journal_path=tmp_path/'empty.sqlite').start()
    client=DeviceClient('127.0.0.1',device.port)
    try:
        report=resolve(client,'NO_TARGET',0)
        assert report['action']=='ALREADY_OFF'
        assert report['command_id']==0
        assert report['next_command_id']==1
        assert client.status()['execution_count']==0
    finally:device.stop()


def test_unexpected_ack_or_reserved_id_is_not_permission_to_release(resolve,rig):
    device,client=rig;device.set_feedback(-6.,False)
    client.command(2,True)
    assert resolve(client,'SEAL_NOT_CONFIRMED',1)['action']=='RETAIN'
    client.cancel(1)  # ack=1 but max=2; a different write is known to exist
    assert resolve(client,'SEAL_NOT_CONFIRMED',1)['action']=='RETAIN'
    assert client.status()['valve'] is True
    assert client.status()['execution_count']==2


def test_fresh_status_timeout_retains_output_without_using_cached_status(resolve,rig):
    device,client=rig;device.set_feedback(-6.,False)
    client.status()
    device.inject_fault('delay_response')
    report=resolve(client,'SEAL_NOT_CONFIRMED',1)
    assert report['action']=='RETAIN'
    assert report['status'] is None
    assert client.status()['valve'] is True
    assert client.status()['execution_count']==1


def test_unfinished_intent_and_recovery_latch_retain_output(resolve,rig):
    device,client=rig;device.set_feedback(-6.,False)
    device.inject_fault('interrupt_after_intent')
    with pytest.raises(DeviceError):client.command(2,False)
    report=resolve(client,'SEAL_NOT_CONFIRMED',2)
    assert report['action']=='RETAIN'
    assert client.status()['valve'] is True
    assert client.status()['execution_count']==1


def test_competing_writer_cannot_turn_conflicting_id_into_release(resolve,rig):
    device,client=rig;device.set_feedback(-6.,False)
    competitor=DeviceClient('127.0.0.1',device.port)
    class RacingClient:
        def status(self):return client.status()
        def command(self,command_id,valve):
            competitor.command(command_id,True)
            return client.command(command_id,valve)
    report=resolve(RacingClient(),'SEAL_NOT_CONFIRMED',1)
    assert report['action']=='OFF_UNCONFIRMED'
    assert report['command_id']==2
    assert report['next_command_id']==3
    assert report['status'] is None
    assert client.status()['valve'] is True


def test_lost_off_result_does_not_claim_it_retained_or_confirmed_output(resolve,rig):
    device,client=rig;device.set_feedback(-6.,False)
    class LostResultClient:
        def status(self):return client.status()
        def command(self,command_id,valve):
            client.command(command_id,valve)
            raise TimeoutError('response unavailable after actual application')
    report=resolve(LostResultClient(),'SEAL_NOT_CONFIRMED',1)
    assert report['action']=='OFF_UNCONFIRMED'
    assert report['status'] is None
    assert report['command_id']==2
    assert client.status()['valve'] is False  # actual state, never falsely reported as retained
    assert client.status()['execution_count']==2


def test_another_writer_after_off_is_detected_by_final_fresh_status(resolve,rig):
    device,client=rig;device.set_feedback(-6.,False)
    class LaterWriter:
        def status(self):return client.status()
        def command(self,command_id,valve):
            confirmed=client.command(command_id,valve)
            client.command(command_id+1,True)
            return confirmed
    report=resolve(LaterWriter(),'SEAL_NOT_CONFIRMED',1)
    assert report['action']=='OFF_UNCONFIRMED'
    assert report['command_id']==2
    assert report['status']['ack_id']==3
    assert client.status()['valve'] is True


@pytest.mark.parametrize('patch', [{'pressure_kpa':float('nan')},{'pressure_kpa':True},{'attached':None},
                                  {'valve':1},{'ack_id':True},{'error':None},{'max_command_id':0}])
def test_malformed_status_fails_closed_before_output_write(resolve,rig,patch):
    device,client=rig;device.set_feedback(-6.,False)
    snapshot=dict(client.status(),**patch)
    class InvalidStatus:
        def status(self):return snapshot
        def command(self,command_id,valve):return client.command(command_id,valve)
    assert resolve(InvalidStatus(),'SEAL_NOT_CONFIRMED',1)['action']=='RETAIN'
    assert client.status()['valve'] is True
    assert client.status()['execution_count']==1


def test_exhausted_uint32_space_never_wraps_to_release(resolve,tmp_path):
    device=DeviceEmulator(journal_path=tmp_path/'max.sqlite').start()
    client=DeviceClient('127.0.0.1',device.port)
    try:
        client.command(4294967295,True);device.set_feedback(-6.,False)
        report=resolve(client,'SEAL_NOT_CONFIRMED',4294967295)
        assert report['action']=='RETAIN'
        assert report['next_command_id'] is None
        assert client.status()['valve'] is True
    finally:device.stop()


def test_carrying_veto_does_not_hide_device_recovery_uncertainty(resolve,rig):
    device,client=rig
    device.inject_fault('interrupt_after_intent')
    with pytest.raises(DeviceError):client.command(2,False)
    report=resolve(client,'CANCELLED',2,carrying=True)
    assert report['action']=='RETAIN'
    assert report['output_uncertain'] is True
    assert client.status()['valve'] is True


def test_off_reply_with_wrong_snapshot_never_claims_confirmation(resolve,rig):
    device,client=rig;device.set_feedback(-6.,False)
    class WrongReceipt:
        def status(self):return client.status()
        def command(self,command_id,valve):
            applied=client.command(command_id,valve)
            return dict(applied,ack_id=command_id-1)
    report=resolve(WrongReceipt(),'SEAL_NOT_CONFIRMED',1)
    assert report['action']=='OFF_UNCONFIRMED'
    assert report['output_uncertain'] is True
    assert client.status()['valve'] is False
    assert client.status()['execution_count']==2


def test_final_status_timeout_after_actual_off_remains_unconfirmed(resolve,rig):
    device,client=rig;device.set_feedback(-6.,False)
    class FinalReadTimeout:
        def status(self):return client.status()
        def command(self,command_id,valve):
            applied=client.command(command_id,valve)
            device.inject_fault('delay_response')
            return applied
    report=resolve(FinalReadTimeout(),'SEAL_NOT_CONFIRMED',1)
    assert report['action']=='OFF_UNCONFIRMED'
    assert report['status'] is None
    assert report['command_id']==2
    assert client.status()['valve'] is False
    assert client.status()['execution_count']==2
