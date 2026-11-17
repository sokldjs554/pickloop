import pytest
from pickloop.evaluation import summarize,validate_pairs

def row(seed,policy,success,first,duration):
    return {'seed':seed,'fault':'normal','policy':policy,'success':success,'sku':'SKU-RED-A','status':'COMPLETED' if success else 'HELD','metrics':{'first_attempt_success':first,'first_attempt_pick_success':first,'sim_duration_s':duration,'wall_duration_s':1.,'recovery_sim_s':None if first else 2.,'wrong_placements':0,'drops':0,'collisions':0,'retries':0 if first else 1,'timeout':False,'selection_attempted':True,'selection_correct':True,'position_error_m':.001}}

def test_failure_times_and_recovery_denominator_are_included():
    rows=[row(1,'recovery',True,True,10),row(2,'recovery',True,False,20),row(3,'recovery',False,False,60)]
    s=summarize(rows)
    assert s['completion_rate']==pytest.approx(2/3)
    assert s['recovery_rate']==.5 and s['first_attempt_failures']==2
    assert s['throughput_per_sim_hour']==80
    assert s['mean_sim_s']==30

def test_unpaired_or_duplicate_conditions_rejected():
    with pytest.raises(ValueError):validate_pairs([row(1,'baseline',True,True,10)])
    with pytest.raises(ValueError):validate_pairs([row(1,'baseline',True,True,10)]*2)
