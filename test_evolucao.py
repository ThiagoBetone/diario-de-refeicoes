from fastapi.testclient import TestClient
from main import create_app


def test_excluir_refeicoes_apenas_da_evolucao(tmp_path):
    banco=tmp_path/'filtro.db'
    with TestClient(create_app(banco)) as c:
        c.put('/perfil',json=dict(idade=30,peso_kg=80,altura_cm=180,sexo_formula='masculino',vigente_desde='2026-09-01'))
        ids=[]
        for kcal in [1000,1200]:
            ids.append(c.post('/refeicoes',json=dict(nome='Refeição',data='2026-09-01',calorias=kcal,proteinas=1,carboidratos=1,gorduras=1)).json()['id'])
        assert c.get('/evolucao').json()['dias'][0]['saldo']==420
        url=f'/evolucao/refeicoes/{ids[0]}'
        assert c.put(url,json={'excluida':True}).status_code==200
        assert c.put(url,json={'excluida':True}).status_code==200
        filtrado=c.get('/evolucao').json()
        assert filtrado['dias'][0]['consumidas']==1200
        assert filtrado['dias'][0]['saldo']==-580
        assert c.get('/resumo-diario?data=2026-09-01').json()['calorias']==2200
        assert c.get('/balanco-diario?data=2026-09-01').json()['consumidas']==2200
        assert len(c.get('/refeicoes?data=2026-09-01').json())==2
        assert c.put('/evolucao/refeicoes/99999',json={'excluida':True}).status_code==404
        assert c.put(url,json={'excluida':'false'}).status_code==422
    with TestClient(create_app(banco)) as c:
        assert c.get('/evolucao').json()['dias'][0]['consumidas']==1200
        c.put(f'/evolucao/refeicoes/{ids[1]}',json={'excluida':True})
        dia=c.get('/evolucao').json()['dias'][0]
        assert dia['consumidas'] is None and dia['saldo'] is None
        assert dia['tmb']==1780
        c.put(url,json={'excluida':False})
        assert c.get('/evolucao').json()['dias'][0]['consumidas']==1000
        c.put(f'/evolucao/refeicoes/{ids[1]}',json={'excluida':False})
        assert c.get('/evolucao').json()['dias'][0]['saldo']==420


def test_medidas_e_historico(tmp_path):
    banco = tmp_path/'teste.db'
    with TestClient(create_app(banco)) as c:
        assert c.put('/perfil/medidas',json=dict(data='2026-09-01',peso_kg=80)).status_code == 409
        c.put('/perfil',json=dict(idade=30,peso_kg=80,altura_cm=180,sexo_formula='masculino',vigente_desde='2026-09-01'))
        assert c.put('/perfil/medidas',json=dict(data='2026-09-01',peso_kg=80,cintura_cm=90)).status_code == 200
        c.put('/perfil/medidas',json=dict(data='2026-09-03',peso_kg=79,cintura_cm=89))
        c.put('/perfil/medidas',json=dict(data='2026-09-03',peso_kg=78.5,cintura_cm=88.5))
        for erro in [dict(peso_kg=-1),dict(cintura_cm=0),dict(peso_kg='NaN'),{}]:
            assert c.put('/perfil/medidas',json=dict(data='2026-09-04',**erro)).status_code == 422
        rows=c.get('/perfil/medidas').json()
        assert len(rows)==2 and rows[-1]['peso_kg']==78.5
        assert c.get('/perfil').json()['peso_kg']==80
    with TestClient(create_app(banco)) as c:
        assert c.get('/perfil/medidas').json()==rows


def test_timeline_sem_falsos_deficits(tmp_path):
    with TestClient(create_app(tmp_path/'teste.db')) as c:
        assert c.get('/evolucao').json()['dias']==[]
        def refeicao(data,kcal):
            c.post('/refeicoes',json=dict(nome='Refeição',data=data,calorias=kcal,proteinas=1,carboidratos=1,gorduras=1))
        refeicao('2026-09-01',1000)
        c.put('/perfil',json=dict(idade=30,peso_kg=80,altura_cm=180,sexo_formula='masculino',vigente_desde='2026-09-02'))
        refeicao('2026-09-02',1500)
        refeicao('2026-09-04',1200)
        refeicao('2026-09-04',1200)
        c.post('/treinos',json=dict(nome='Corrida',data='2026-09-04',calorias=200))
        c.post('/treinos',json=dict(nome='Corrida',data='2026-09-06',calorias=300))
        c.put('/perfil',json=dict(idade=30,peso_kg=75,altura_cm=180,sexo_formula='masculino',vigente_desde='2026-09-04'))
        rows=c.get('/evolucao').json()['dias']
        assert [r['data'] for r in rows]==['2026-09-01','2026-09-02','2026-09-04','2026-09-06']
        assert rows[0]['saldo'] is None
        assert rows[1]['saldo']==-280
        assert rows[2]['gasto_referencia']==1930 and rows[2]['saldo']==470
        assert rows[3]['consumidas'] is None and rows[3]['saldo'] is None
