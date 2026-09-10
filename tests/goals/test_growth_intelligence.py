from scripts.growth_intelligence import window,site_queries,propose_actions

def test_complete_day_window_is_exclusive_and_thirty_days():
    start,end=window(30,'2026-09-09')
    assert start.isoformat()=='2026-08-10T00:00:00-03:00'
    assert (end-start).days==30
    for name,query in site_queries(start,end).items():
        assert query.lower().startswith(('select','with'))
        assert 'public.' in query

def test_missing_data_is_not_zero_sales():
    actions=propose_actions({'sources':{'site':{'status':'unavailable'},'cakto':{'status':'unavailable'}}})
    assert len([a for a in actions if a['priority']=='P0'])==2
    assert not any('venda' in a['action'] for a in actions)

def test_cohort_proposal_stays_hypothesis_and_draft():
    actions=propose_actions({'sources':{'site':{'status':'ok','data':{'classroom_cohort':[{'unlocked_sessions':39,'offer_click_sessions':0}]}}}})
    assert actions[0]['hypothesis'] is True
    assert actions[-1]['execution'].startswith('draft_only')

def test_architecture_is_counted_separately_from_historical_challenge():
    queries=site_queries(*window(30,'2026-09-09'))
    for key,label in [('classroom_cohort','conhecer-arquitetura'),('bio_cohort','sessao-arquitetura')]:
        assert 'architecture_click_sessions' in queries[key]
        assert 'offer_click_sessions' in queries[key]
        assert label in queries[key]
        assert "c.created_at>=e.entered" in queries[key]
    assert 'arquitetura-checkout' in queries['architecture_cohort']

def test_architecture_clicks_do_not_trigger_false_zero_offer_alert():
    actions=propose_actions({'sources':{'site':{'status':'ok','data':{'classroom_cohort':[{'unlocked_sessions':39,'offer_click_sessions':0,'architecture_click_sessions':2}]}}}})
    assert not any('Testar ponte aula' in a['action'] for a in actions)
